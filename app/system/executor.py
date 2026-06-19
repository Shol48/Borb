"""System Execution Layer.

Executes the structured actions planned by the agent. Borb works exclusively
through the shell, so the only action type is a shell command — every task
(creating, reading or deleting files, browsing, system tasks, ...) is expressed
as a shell command. The executor itself does not make policy decisions - it
simply executes. Gating is performed by the agent core via the
:class:`~app.system.policy.PolicyEngine` before an action reaches here.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

from app.config import Settings
from app.schemas import (
    Action,
    ActionResult,
    ActionType,
    ShellAction,
)

# Cap captured shell output so a chatty command can not blow up the response.
MAX_OUTPUT_CHARS = 20_000


class SystemExecutor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def execute(self, action: Action) -> ActionResult:
        try:
            if isinstance(action, ShellAction):
                return await self._run_shell(action)
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

        # Run the command in a worker thread via blocking ``subprocess.run``
        # rather than ``asyncio.create_subprocess_shell``. The asyncio
        # subprocess API is unsupported on the Windows ``SelectorEventLoop``
        # (the loop uvicorn runs on by default) and raises ``NotImplementedError``
        # there. Offloading a blocking call keeps shell execution working on
        # every platform regardless of the active event loop policy.
        try:
            completed = await asyncio.to_thread(self._run_shell_blocking, action.command, cwd)
        except subprocess.TimeoutExpired as exc:
            return ActionResult(
                type=ActionType.SHELL,
                intent=action.intent,
                command=action.command,
                stdout=_clip(_as_text(exc.stdout)),
                stderr=_clip(_as_text(exc.stderr)),
                status="error",
                error=f"command timed out after {self.settings.shell_timeout}s",
            )

        return ActionResult(
            type=ActionType.SHELL,
            intent=action.intent,
            command=action.command,
            exit_code=completed.returncode,
            stdout=_clip(completed.stdout),
            stderr=_clip(completed.stderr),
            status="executed",
        )

    def _run_shell_blocking(self, command: str, cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=self.settings.shell_timeout,
        )


def _as_text(value: object) -> str:
    """Normalise possibly-``None``/bytes partial output (e.g. from a timeout)."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _clip(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"
    return text
