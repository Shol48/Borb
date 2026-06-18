"""System Execution Layer.

Executes the structured actions planned by the agent: shell commands, file
reads/writes and directory listings. The executor itself does not make policy
decisions - it simply executes. Gating is performed by the agent core via the
:class:`~app.system.policy.PolicyEngine` before an action reaches here.
"""

from __future__ import annotations

import asyncio
import os

from app.config import Settings
from app.schemas import (
    Action,
    ActionResult,
    ActionType,
    ListDirAction,
    ReadFileAction,
    ShellAction,
    WriteFileAction,
)
from app.system.filesystem import Filesystem

# Cap captured shell output so a chatty command can not blow up the response.
MAX_OUTPUT_CHARS = 20_000


class SystemExecutor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fs = Filesystem()

    async def execute(self, action: Action) -> ActionResult:
        try:
            if isinstance(action, ShellAction):
                return await self._run_shell(action)
            if isinstance(action, ReadFileAction):
                return self._read_file(action)
            if isinstance(action, WriteFileAction):
                return self._write_file(action)
            if isinstance(action, ListDirAction):
                return self._list_dir(action)
            return ActionResult(
                type=getattr(action, "type", ActionType.SHELL),
                status="error",
                error=f"unsupported action: {action!r}",
            )
        except Exception as exc:  # surface execution errors as results, not 500s
            return ActionResult(
                type=getattr(action, "type", ActionType.SHELL),
                intent=getattr(action, "intent", None),
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )

    # --- shell -------------------------------------------------------------- #
    async def _run_shell(self, action: ShellAction) -> ActionResult:
        cwd = action.cwd or self.settings.workspace_root or os.getcwd()
        proc = await asyncio.create_subprocess_shell(
            action.command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.settings.shell_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ActionResult(
                type=ActionType.SHELL,
                intent=action.intent,
                command=action.command,
                status="error",
                error=f"command timed out after {self.settings.shell_timeout}s",
            )

        return ActionResult(
            type=ActionType.SHELL,
            intent=action.intent,
            command=action.command,
            exit_code=proc.returncode,
            stdout=_clip(stdout_b.decode("utf-8", errors="replace")),
            stderr=_clip(stderr_b.decode("utf-8", errors="replace")),
            status="executed",
        )

    # --- filesystem --------------------------------------------------------- #
    def _read_file(self, action: ReadFileAction) -> ActionResult:
        content = self.fs.read_file(action.path)
        return ActionResult(
            type=ActionType.READ_FILE,
            intent=action.intent,
            path=action.path,
            output=_clip(content),
            status="executed",
        )

    def _write_file(self, action: WriteFileAction) -> ActionResult:
        written = self.fs.write_file(action.path, action.content)
        return ActionResult(
            type=ActionType.WRITE_FILE,
            intent=action.intent,
            path=action.path,
            output=f"wrote {written} bytes to {action.path}",
            status="executed",
        )

    def _list_dir(self, action: ListDirAction) -> ActionResult:
        entries = self.fs.list_dir(action.path)
        return ActionResult(
            type=ActionType.LIST_DIR,
            intent=action.intent,
            path=action.path,
            output=_clip("\n".join(entries)),
            status="executed",
        )


def _clip(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"
    return text
