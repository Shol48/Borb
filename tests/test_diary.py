import pytest

from app.agent.core import MAIN_SESSION, AgentCore, SessionStore
from app.agent.diary import diary_filename, write_diary
from app.audit.logger import AuditLogger
from app.config import AuthorityMode, Settings
from app.llm.base import LLMProviderBase, StreamChunk
from app.system.executor import SystemExecutor
from app.system.policy import PolicyEngine


class FakeLLM(LLMProviderBase):
    def __init__(self, reply: str):
        super().__init__(model="fake")
        self._reply = reply

    async def chat(self, messages, *, temperature=None):
        return self._reply

    async def stream(self, messages, *, temperature=None):
        yield StreamChunk(kind="content", text=self._reply)


def _agent(settings, llm):
    return AgentCore(
        settings=settings,
        llm=llm,
        executor=SystemExecutor(settings),
        policy=PolicyEngine(settings),
        audit=AuditLogger(settings),
        sessions=SessionStore(),
    )


def test_diary_filename_format():
    from datetime import datetime

    name = diary_filename(datetime(2026, 6, 19))
    assert name == "20260619_Borb_Diary_Entry.md"


@pytest.mark.asyncio
async def test_write_diary_persists_file_and_clears_context(tmp_path):
    settings = Settings(
        authority_mode=AuthorityMode.AUTHORITY,
        diary_dir=str(tmp_path / "Borb_Diary"),
        audit_log=False,
    )
    agent = _agent(settings, FakeLLM("Today was a good day. I learned a lot."))

    # Seed some live context that should be wiped afterwards.
    agent.sessions.reset_system(MAIN_SESSION, "SYS")
    agent.sessions.history(MAIN_SESSION).append({"role": "user", "content": "hi"})

    path = await write_diary(agent)

    assert path.exists()
    assert path.name == diary_filename()
    assert "learned" in path.read_text(encoding="utf-8")

    # Context cleared down to the system message only.
    history = agent.sessions.history(MAIN_SESSION)
    assert len(history) == 1
    assert history[0]["role"] == "system"
