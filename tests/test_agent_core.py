import json

import pytest

from app.agent.core import MAIN_SESSION, AgentCore, SessionStore
from app.audit.logger import AuditLogger
from app.config import AuthorityMode, Settings
from app.llm.base import LLMProviderBase, StreamChunk
from app.schemas import ChatRequest
from app.system.executor import SystemExecutor
from app.system.policy import PolicyEngine


class ScriptedLLM(LLMProviderBase):
    """Returns pre-scripted replies in order."""

    def __init__(self, replies):
        super().__init__(model="scripted")
        self._replies = list(replies)
        self.calls = []

    async def chat(self, messages, *, temperature=None):
        self.calls.append(messages[-1]["content"])
        return self._replies.pop(0)

    async def stream(self, messages, *, temperature=None):
        self.calls.append(messages[-1]["content"])
        yield StreamChunk(kind="content", text=self._replies.pop(0))


def _agent(settings, llm):
    return AgentCore(
        settings=settings,
        llm=llm,
        executor=SystemExecutor(settings),
        policy=PolicyEngine(settings),
        audit=AuditLogger(settings),
        sessions=SessionStore(),
    )


@pytest.mark.asyncio
async def test_plain_answer_no_actions():
    settings = Settings(authority_mode=AuthorityMode.AUTHORITY, audit_log=False)
    llm = ScriptedLLM([json.dumps({"answer": "Hi there", "done": True})])
    agent = _agent(settings, llm)
    resp = await agent.handle(ChatRequest(prompt="hello"))
    assert resp.answer == "Hi there"
    assert resp.actions == []


@pytest.mark.asyncio
async def test_executes_shell_then_finishes(tmp_path):
    settings = Settings(
        authority_mode=AuthorityMode.AUTHORITY,
        workspace_root=str(tmp_path),
        audit_log=False,
    )
    replies = [
        json.dumps(
            {
                "done": False,
                "actions": [{"type": "shell", "command": "echo borb"}],
            }
        ),
        json.dumps({"answer": "I ran echo.", "done": True}),
    ]
    agent = _agent(settings, ScriptedLLM(replies))
    resp = await agent.handle(ChatRequest(prompt="run echo"))
    assert resp.answer == "I ran echo."
    assert len(resp.actions) == 1
    assert resp.actions[0].exit_code == 0
    assert "borb" in resp.actions[0].stdout


@pytest.mark.asyncio
async def test_normal_mode_confirmation_pauses(tmp_path):
    settings = Settings(
        authority_mode=AuthorityMode.NORMAL,
        workspace_root=str(tmp_path),
        audit_log=False,
    )
    replies = [
        json.dumps(
            {
                "done": False,
                "actions": [{"type": "shell", "command": "rm something"}],
            }
        )
    ]
    agent = _agent(settings, ScriptedLLM(replies))
    resp = await agent.handle(ChatRequest(prompt="delete stuff"))
    assert len(resp.pending_confirmations) == 1
    assert resp.pending_confirmations[0].decision.decision.value == "confirm"


@pytest.mark.asyncio
async def test_global_memory_accumulates_without_session_id():
    settings = Settings(authority_mode=AuthorityMode.AUTHORITY, audit_log=False)
    llm = ScriptedLLM(
        [
            json.dumps({"answer": "first", "done": True}),
            json.dumps({"answer": "second", "done": True}),
        ]
    )
    agent = _agent(settings, llm)

    r1 = await agent.handle(ChatRequest(prompt="hello"))
    r2 = await agent.handle(ChatRequest(prompt="and again"))

    # Both requests fall into the same default conversation.
    assert r1.session_id == MAIN_SESSION
    assert r2.session_id == MAIN_SESSION
    history = agent.sessions.history(MAIN_SESSION)
    assert history[0]["role"] == "system"
    # system + (user/assistant) * 2 turns
    assert [m["role"] for m in history[1:]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_session_clear_keeps_system_message():
    store = SessionStore()
    store.reset_system("s", "SYSTEM")
    store.history("s").append({"role": "user", "content": "hi"})
    store.history("s").append({"role": "assistant", "content": "yo"})

    store.clear("s")

    history = store.history("s")
    assert len(history) == 1
    assert history[0] == {"role": "system", "content": "SYSTEM"}


@pytest.mark.asyncio
async def test_handle_stream_emits_events(tmp_path):
    settings = Settings(
        authority_mode=AuthorityMode.AUTHORITY,
        workspace_root=str(tmp_path),
        audit_log=False,
    )
    replies = [
        'Let me run echo.\n```json\n'
        + json.dumps({"actions": [{"type": "shell", "command": "echo borb"}], "done": False})
        + "\n```",
        "All done.",
    ]
    agent = _agent(settings, ScriptedLLM(replies))

    events = [e async for e in agent.handle_stream(ChatRequest(prompt="run echo"))]
    types = [e["type"] for e in events]

    assert types[0] == "start"
    assert "tool_call" in types
    assert "tool_result" in types
    assert types[-1] == "done"

    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert tool_result["status"] == "executed"
    assert "borb" in (tool_result["stdout"] or "")

    answers = "".join(e["text"] for e in events if e["type"] == "answer")
    assert "Let me run echo." in answers
