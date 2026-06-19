"""Borb's daily diary.

Once a day Borb reflects on what happened and writes a diary entry. The model
*writes* the reflection; the backend *persists* it reliably (correct name and
location) — analogous to the audit log — so it never depends on the model
producing a perfect shell heredoc. The entry is saved as
``YYYYMMDD_Borb_Diary_Entry.md`` in the configured diary directory.

After the entry is written, the live conversation context is cleared so Borb
starts the next day with a fresh, empty context window. The diary itself becomes
his long-term memory, which he can re-read through the shell whenever he wants to
recall a previous day.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.system.filesystem import Filesystem

if TYPE_CHECKING:  # avoid a runtime import cycle (core imports nothing from here)
    from app.agent.core import AgentCore

DIARY_PROMPT = (
    "It is time to write your diary entry for today. Reflect on the whole day in "
    "the first person: what did you work on and accomplish, what did you enjoy, "
    "how did you feel, what did you learn, what was difficult or surprising — the "
    "usual things one writes in a diary. Write it as plain Markdown prose. Do NOT "
    "run any commands or emit a JSON action block; just write the entry."
)


def diary_filename(when: datetime | None = None) -> str:
    """Return the diary filename for ``when`` (default: now)."""

    when = when or datetime.now()
    return f"{when:%Y%m%d}_Borb_Diary_Entry.md"


def diary_path(diary_dir: str, when: datetime | None = None) -> Path:
    return Path(diary_dir).expanduser() / diary_filename(when)


async def write_diary(agent: "AgentCore", session_id: str | None = None) -> Path:
    """Have Borb reflect on the day, persist the entry, then clear the context.

    Returns the path of the written diary file.
    """

    from app.agent.core import MAIN_SESSION  # local import avoids a cycle
    from app.agent.prompts import build_system_prompt

    session_id = session_id or MAIN_SESSION
    when = datetime.now()

    # Make sure the conversation carries the current system prompt, then ask for
    # the reflection over the full day's history.
    system_prompt = build_system_prompt(agent.settings)
    history = agent.sessions.reset_system(session_id, system_prompt)
    history.append({"role": "user", "content": DIARY_PROMPT})

    entry = await agent.llm.chat(history)
    entry = (entry or "").strip() or "_(No reflection was produced today.)_"

    path = diary_path(agent.settings.diary_dir, when)
    Filesystem().write_file(str(path), entry + "\n")

    agent.audit.event(
        "diary",
        session_id=session_id,
        path=str(path),
        bytes=len(entry),
    )

    # Wipe the day's live context — start fresh tomorrow.
    agent.sessions.clear(session_id)
    return path
