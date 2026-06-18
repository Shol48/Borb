"""Audit logging for Borb.

Every important request, policy decision, action, command, result and error is
recorded as a structured (JSON-per-line) audit event. Output goes to a standard
``logging`` logger and, if configured, to an append-only audit file.
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict, Optional

from app.config import Settings, get_settings

_logger = logging.getLogger("borb.audit")


class AuditLogger:
    """Writes structured audit events."""

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.audit_log
        self._file = settings.audit_log_file

    def event(self, event_type: str, **fields: Any) -> Dict[str, Any]:
        """Record a single audit event and return it."""

        record: Dict[str, Any] = {
            "ts": time.time(),
            "event": event_type,
            **fields,
        }
        if not self._enabled:
            return record

        line = json.dumps(record, default=str, ensure_ascii=False)
        _logger.info(line)
        if self._file:
            try:
                with open(self._file, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:  # pragma: no cover - best effort
                _logger.warning("audit: failed to write audit file: %s", exc)
        return record

    # convenience helpers -------------------------------------------------- #
    def request(self, session_id: str, **fields: Any) -> None:
        self.event("request", session_id=session_id, **fields)

    def decision(self, session_id: str, **fields: Any) -> None:
        self.event("policy_decision", session_id=session_id, **fields)

    def action(self, session_id: str, **fields: Any) -> None:
        self.event("action", session_id=session_id, **fields)

    def result(self, session_id: str, **fields: Any) -> None:
        self.event("action_result", session_id=session_id, **fields)

    def error(self, session_id: Optional[str], **fields: Any) -> None:
        self.event("error", session_id=session_id, **fields)


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    return AuditLogger(get_settings())
