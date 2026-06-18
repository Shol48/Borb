import json

import pytest

from app.agent.core import AgentCore, SessionStore
from app.audit.logger import AuditLogger
from app.config import AuthorityMode, Settings
from app.llm.base import LLMProviderBase
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
