"""System prompt construction for the agent core.

The actual prompt text lives in a single editable template file next to this
module: ``system_prompt.md``. Edit that file to change Borb's persona, the
description of the authority modes, or the JSON action protocol — no code change
required.

The template uses ``string.Template`` (``$placeholder``) substitution so that
the literal JSON braces ``{ }`` in the protocol stay untouched. Available
placeholders:

* ``$authority_mode``  -> the active mode (``normal`` / ``authority``),
* ``$workspace_root``  -> the configured workspace root,
* ``$diary_dir``       -> the folder where Borb's diary entries live.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from app.config import Settings

#: Single source of truth for the editable system prompt text.
SYSTEM_PROMPT_FILE = Path(__file__).with_name("system_prompt.md")


def build_system_prompt(settings: Settings) -> str:
    template = Template(SYSTEM_PROMPT_FILE.read_text(encoding="utf-8"))
    return template.safe_substitute(
        authority_mode=settings.authority_mode.value,
        workspace_root=settings.workspace_root,
        diary_dir=settings.diary_dir,
    ).strip()


def format_action_results(results: list[dict]) -> str:
    """Render executed action results as a user-role observation message."""

    import json

    return (
        "Results of the actions you requested (continue, or set done=true):\n"
        + json.dumps(results, indent=2, default=str, ensure_ascii=False)
    )
