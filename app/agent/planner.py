"""Action planner.

Parses the model's reply into a structured :class:`Plan`. The model is asked to
reply with a single JSON object, but real models add stray prose or markdown
fences, so the planner extracts and validates the first JSON object it finds and
degrades gracefully to a plain answer when no valid plan is present.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List

from pydantic import TypeAdapter, ValidationError

from app.schemas import Action

_action_adapter: TypeAdapter[Action] = TypeAdapter(Action)


@dataclass
class Plan:
    answer: str = ""
    actions: List[Action] = field(default_factory=list)
    done: bool = True
    raw: str = ""


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced top-level JSON object substring, if any."""

    # Strip ```json ... ``` fences if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)

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
                return text[start : i + 1]
    return None


def parse_plan(text: str) -> Plan:
    text = (text or "").strip()
    blob = _extract_json_object(text)
    if blob is None:
        # No JSON at all -> treat the whole reply as a final answer.
        return Plan(answer=text, actions=[], done=True, raw=text)

    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return Plan(answer=text, actions=[], done=True, raw=text)

    if not isinstance(data, dict):
        return Plan(answer=text, actions=[], done=True, raw=text)

    answer = str(data.get("answer", "") or "")
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
