"""Agent Core.

Processes user requests: builds the system prompt, manages conversation context,
plans structured actions via the LLM, lets the Policy/Authority layer decide on
each action, runs the allowed ones through the System Executor, and loops until
the model is done (or the step budget is exhausted).
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List

from app.agent.planner import Plan, parse_plan
from app.agent.prompts import build_system_prompt, format_action_results
from app.audit.logger import AuditLogger
from app.config import Settings
from app.llm.base import LLMProviderBase, Message
from app.schemas import (
    Action,
    ActionResult,
    ChatRequest,
    ChatResponse,
    PendingConfirmation,
    PolicyDecisionType,
)
from app.system.executor import SystemExecutor
from app.system.policy import PolicyEngine

#: Borb has a single, continuous memory while the process runs. Requests that do
#: not carry an explicit session id all share this default conversation, so the
#: frontend never has to resend the chat history.
MAIN_SESSION = "borb-main"


class SessionStore:
    """Minimal in-memory conversation store keyed by session id."""

    def __init__(self) -> None:
        self._sessions: Dict[str, List[Message]] = {}

    def history(self, session_id: str) -> List[Message]:
        return self._sessions.setdefault(session_id, [])

    def reset_system(self, session_id: str, system_prompt: str) -> List[Message]:
        history = self._sessions.setdefault(session_id, [])
        if not history or history[0]["role"] != "system":
            history.insert(0, {"role": "system", "content": system_prompt})
        else:
            history[0]["content"] = system_prompt
        return history

    def clear(self, session_id: str) -> None:
        """Drop the conversation history, keeping only the system message.

        Used after a diary entry is written so Borb starts the next day with a
        fresh, empty context window.
        """

        history = self._sessions.get(session_id)
        if not history:
            return
        if history and history[0]["role"] == "system":
            del history[1:]
        else:
            history.clear()


class AgentCore:
    def __init__(
        self,
        settings: Settings,
        llm: LLMProviderBase,
        executor: SystemExecutor,
        policy: PolicyEngine,
        audit: AuditLogger,
        sessions: SessionStore | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.executor = executor
        self.policy = policy
        self.audit = audit
        self.sessions = sessions or SessionStore()

    async def handle(self, request: ChatRequest) -> ChatResponse:
        session_id = request.session_id or MAIN_SESSION
        self.audit.request(
            session_id,
            prompt=request.prompt,
            frontend=request.frontend,
            workspace=request.workspace,
            authority_mode=self.settings.authority_mode.value,
        )

        system_prompt = build_system_prompt(self.settings)
        history = self.sessions.reset_system(session_id, system_prompt)
        history.append({"role": "user", "content": request.prompt})

        executed: List[ActionResult] = []
        pending: List[PendingConfirmation] = []
        final_answer = ""
        steps = 0

        for step in range(self.settings.agent_max_steps):
            steps = step + 1
            reply = await self.llm.chat(history)
            history.append({"role": "assistant", "content": reply})
            plan: Plan = parse_plan(reply)

            if not plan.actions:
                final_answer = plan.answer
                break

            if not request.execute_actions:
                final_answer = plan.answer
                for action in plan.actions:
                    pending.append(
                        PendingConfirmation(
                            action=_dump(action),
                            decision=self.policy.evaluate(action),
                        )
                    )
                break

            step_results, step_pending, stop = await self._run_actions(
                session_id, plan.actions
            )
            executed.extend(step_results)
            pending.extend(step_pending)

            # Feed results back to the model so it can continue the loop.
            observation = format_action_results(
                [r.model_dump(exclude_none=True) for r in step_results]
                + [
                    {"action": p.action, "status": "confirm_required",
                     "decision": p.decision.model_dump()}
                    for p in step_pending
                ]
            )
            history.append({"role": "user", "content": observation})

            if stop:
                # An action requires confirmation -> pause the loop in normal mode.
                final_answer = plan.answer or (
                    "Some actions require your confirmation before I can continue."
                )
                break

            final_answer = plan.answer
        else:
            # Step budget exhausted.
            final_answer = final_answer or (
                "Reached the maximum number of agent steps without finishing."
            )

        return ChatResponse(
            answer=final_answer,
            session_id=session_id,
            authority_mode=self.settings.authority_mode.value,
            actions=executed,
            pending_confirmations=pending,
            steps=steps,
        )

    async def handle_stream(self, request: ChatRequest) -> AsyncIterator[dict]:
        """Run a request and yield a stream of structured events.

        Event ``type`` values:

        * ``start``       -> session/authority metadata,
        * ``thinking``    -> a chunk of the model's reasoning channel,
        * ``answer``      -> a chunk of the user-facing reply (streamed live),
        * ``tool_call``   -> Borb is about to run a command (what it is doing),
        * ``tool_result`` -> the outcome of that command,
        * ``paused``      -> a command needs confirmation (normal mode),
        * ``done``        -> the turn finished.
        """

        session_id = request.session_id or MAIN_SESSION
        self.audit.request(
            session_id,
            prompt=request.prompt,
            frontend=request.frontend,
            workspace=request.workspace,
            authority_mode=self.settings.authority_mode.value,
        )

        system_prompt = build_system_prompt(self.settings)
        history = self.sessions.reset_system(session_id, system_prompt)
        history.append({"role": "user", "content": request.prompt})

        yield {
            "type": "start",
            "session_id": session_id,
            "authority_mode": self.settings.authority_mode.value,
        }

        steps = 0
        for step in range(self.settings.agent_max_steps):
            steps = step + 1

            # --- stream the model reply, splitting prose from the JSON block --- #
            reply = ""
            buffer = ""
            in_json = False
            async for chunk in self.llm.stream(history):
                if chunk.kind == "thinking":
                    if chunk.text:
                        yield {"type": "thinking", "text": chunk.text}
                    continue
                reply += chunk.text
                if in_json:
                    continue
                buffer += chunk.text
                fence = buffer.find("```")
                if fence != -1:
                    pre = buffer[:fence]
                    if pre:
                        yield {"type": "answer", "text": pre}
                    in_json = True
                    buffer = ""
                else:
                    # Hold back the last 2 chars so a "```" fence split across
                    # chunk boundaries is not streamed to the user as prose.
                    if len(buffer) > 2:
                        yield {"type": "answer", "text": buffer[:-2]}
                        buffer = buffer[-2:]
            if not in_json and buffer:
                yield {"type": "answer", "text": buffer}

            history.append({"role": "assistant", "content": reply})
            plan: Plan = parse_plan(reply)

            if not plan.actions:
                break

            if not request.execute_actions:
                for action in plan.actions:
                    decision = self.policy.evaluate(action)
                    yield {
                        "type": "tool_call",
                        "intent": getattr(action, "intent", None),
                        "command": getattr(action, "command", None),
                        "query": getattr(action, "query", None),
                        "decision": decision.decision.value,
                        "executed": False,
                    }
                break

            stop = False
            step_results: List[ActionResult] = []
            step_pending: List[PendingConfirmation] = []
            for action in plan.actions:
                decision = self.policy.evaluate(action)
                self.audit.decision(
                    session_id,
                    action=_dump(action),
                    decision=decision.decision.value,
                    reason=decision.reason,
                    risk=decision.risk,
                )
                yield {
                    "type": "tool_call",
                    "intent": getattr(action, "intent", None),
                    "command": getattr(action, "command", None),
                    "query": getattr(action, "query", None),
                    "decision": decision.decision.value,
                    "executed": decision.decision == PolicyDecisionType.ALLOW,
                }

                if decision.decision == PolicyDecisionType.BLOCK:
                    result = ActionResult(
                        type=action.type,
                        intent=getattr(action, "intent", None),
                        status="blocked",
                        decision=decision,
                        error=decision.reason,
                    )
                    step_results.append(result)
                    yield {
                        "type": "tool_result",
                        "status": "blocked",
                        "error": decision.reason,
                    }
                    continue

                if decision.decision == PolicyDecisionType.CONFIRM:
                    step_pending.append(
                        PendingConfirmation(action=_dump(action), decision=decision)
                    )
                    stop = True
                    yield {
                        "type": "tool_result",
                        "status": "confirm_required",
                        "reason": decision.reason,
                    }
                    continue

                # ALLOW
                self.audit.action(session_id, action=_dump(action))
                result = await self.executor.execute(action)
                result.decision = decision
                self.audit.result(
                    session_id,
                    type=result.type.value,
                    status=result.status,
                    exit_code=result.exit_code,
                    error=result.error,
                )
                step_results.append(result)
                yield {
                    "type": "tool_result",
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "output": result.output,
                    "error": result.error,
                }

            observation = format_action_results(
                [r.model_dump(exclude_none=True) for r in step_results]
                + [
                    {"action": p.action, "status": "confirm_required",
                     "decision": p.decision.model_dump()}
                    for p in step_pending
                ]
            )
            history.append({"role": "user", "content": observation})

            if stop:
                yield {
                    "type": "paused",
                    "pending_confirmations": [
                        {"action": p.action, "decision": p.decision.model_dump()}
                        for p in step_pending
                    ],
                }
                break

        yield {"type": "done", "session_id": session_id, "steps": steps}

    async def _run_actions(self, session_id: str, actions: List[Action]):
        results: List[ActionResult] = []
        pending: List[PendingConfirmation] = []
        stop = False

        for action in actions:
            decision = self.policy.evaluate(action)
            self.audit.decision(
                session_id,
                action=_dump(action),
                decision=decision.decision.value,
                reason=decision.reason,
                risk=decision.risk,
            )

            if decision.decision == PolicyDecisionType.BLOCK:
                results.append(
                    ActionResult(
                        type=action.type,
                        intent=getattr(action, "intent", None),
                        status="blocked",
                        decision=decision,
                        error=decision.reason,
                    )
                )
                continue

            if decision.decision == PolicyDecisionType.CONFIRM:
                pending.append(
                    PendingConfirmation(action=_dump(action), decision=decision)
                )
                stop = True
                continue

            # ALLOW
            self.audit.action(session_id, action=_dump(action))
            result = await self.executor.execute(action)
            result.decision = decision
            self.audit.result(
                session_id,
                type=result.type.value,
                status=result.status,
                exit_code=result.exit_code,
                error=result.error,
            )
            results.append(result)

        return results, pending, stop


def _dump(action: Action) -> dict:
    return action.model_dump(mode="json", exclude_none=True)
