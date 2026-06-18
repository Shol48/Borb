"""Filesystem access for the System Execution Layer.

Reads and writes files. Path containment against the workspace root is enforced
by the Policy Engine in ``normal`` mode; in ``authority`` mode access is
unrestricted (subject only to OS permissions of the process user).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


# Defensive read cap so an accidental "read /dev/zero" can not exhaust memory.
MAX_READ_BYTES = 1_000_000


class Filesystem:
    def read_file(self, path: str, max_bytes: int = MAX_READ_BYTES) -> str:
        p = Path(path).expanduser()
        data = p.read_bytes()
        truncated = len(data) > max_bytes
        text = data[:max_bytes].decode("utf-8", errors="replace")
        if truncated:
            text += f"\n... [truncated at {max_bytes} bytes]"
        return text

    def write_file(self, path: str, content: str) -> int:
        p = Path(path).expanduser()
        if p.parent and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return len(content)

    def list_dir(self, path: str) -> List[str]:
        p = Path(path).expanduser()
        entries = []
        for entry in sorted(p.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            entries.append(entry.name + suffix)
        return entries

    @staticmethod
    def resolve(path: str) -> str:
        return str(Path(path).expanduser().resolve())

    @staticmethod
    def is_within(path: str, root: str) -> bool:
        """True if ``path`` is contained within ``root`` (after resolution)."""

        try:
            resolved = Path(path).expanduser().resolve()
            root_resolved = Path(root).expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        return root_resolved == resolved or root_resolved in resolved.parents
