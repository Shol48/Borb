"""Action planner.

Parses the model's reply into a structured :class:`Plan`.

Borb replies with natural-language prose first (streamed to the user) and, only
when it wants to act, appends a single fenced ```json block with its shell
actions, e.g.::

    Let me list the files first.

    ```json
    {"actions": [{"type": "shell", "command": "ls -la"}], "done": false}
    ```

The planner extracts that JSON block, treats the prose before it as the answer /
narration, and degrades gracefully to a plain answer when no valid block is
present (older models may also emit a bare JSON object, which is still handled).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from pydantic import TypeAdapter, ValidationError

from app.schemas import Action

_action_adapter: TypeAdapter[Action] = TypeAdapter(Action)


@dataclass
class Plan:
    answer: str = ""
    actions: List[Action] = field(default_factory=list)
    done: bool = True
    raw: str = ""


def _find_json_span(text: str) -> Optional[Tuple[int, int, str]]:
    """Return ``(start, end, blob)`` of the model's JSON object, if any.

    Prefers a fenced ```json ... ``` block; otherwise falls back to the first
    balanced top-level ``{...}`` object. ``start``/``end`` index into ``text``
    and cover the *whole* matched region (including fences), so the caller can
    strip it to recover the surrounding prose.
    """

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.start(), fenced.end(), fenced.group(1)

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1, text[start : i + 1]
    return None


def parse_plan(text: str) -> Plan:
    text = (text or "").strip()
    span = _find_json_span(text)
    if span is None:
        # No JSON at all -> the whole reply is a plain final answer.
        return Plan(answer=text, actions=[], done=True, raw=text)

    start, end, blob = span
    prose = (text[:start] + text[end:]).strip()

    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return Plan(answer=text, actions=[], done=True, raw=text)

    if not isinstance(data, dict):
        return Plan(answer=text, actions=[], done=True, raw=text)

    # The prose around the JSON block is the user-facing answer/narration. Fall
    # back to a legacy in-JSON "answer" field if there was no prose.
    answer = prose or str(data.get("answer", "") or "")
    done = bool(data.get("done", True))

    actions: List[Action] = []
    for item in data.get("actions") or []:
        try:
            actions.append(_action_adapter.validate_python(item))
        except ValidationError:
            # Skip malformed actions rather than failing the whole turn.
            continue

    # If the model gave neither a usable answer nor actions, fall back to raw.
    if not answer and not actions:
        answer = text

    # If there are actions, we are not done regardless of the flag.
    if actions:
        done = False

    return Plan(answer=answer, actions=actions, done=done, raw=text)
