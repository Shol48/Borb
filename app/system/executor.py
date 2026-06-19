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
    WebsearchAction,
)
from app.system.websearch.base import SearchResult, WebsearchProviderBase

# Cap captured shell output so a chatty command can not blow up the response.
MAX_OUTPUT_CHARS = 20_000


class SystemExecutor:
    def __init__(
        self,
        settings: Settings,
        websearch: WebsearchProviderBase | None = None,
    ) -> None:
        self.settings = settings
        # Optional injection (tests); otherwise built lazily from config so the
        # search backend is only constructed when a websearch action arrives.
        self._websearch = websearch

    async def execute(self, action: Action) -> ActionResult:
        try:
            if isinstance(action, ShellAction):
                return await self._run_shell(action)
            if isinstance(action, WebsearchAction):
                return await self._run_websearch(action)
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

    # --- websearch ---------------------------------------------------------- #
    async def _run_websearch(self, action: WebsearchAction) -> ActionResult:
        provider = self._get_websearch_provider()
        max_results = action.max_results or self.settings.websearch_max_results

        try:
            results = await provider.search(action.query, max_results=max_results)
        except Exception as exc:  # network/rate-limit/etc. -> result, not a 500
            return ActionResult(
                type=ActionType.WEBSEARCH,
                intent=action.intent,
                query=action.query,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )

        return ActionResult(
            type=ActionType.WEBSEARCH,
            intent=action.intent,
            query=action.query,
            output=_clip(_format_results(results)),
            status="executed",
        )

    def _get_websearch_provider(self) -> WebsearchProviderBase:
        if self._websearch is None:
            # Imported here to avoid a hard import dependency at module load.
            from app.system.websearch.router import get_websearch_provider

            self._websearch = get_websearch_provider()
        return self._websearch


def _as_text(value: object) -> str:
    """Normalise possibly-``None``/bytes partial output (e.g. from a timeout)."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _format_results(results: list[SearchResult]) -> str:
    """Render search hits as a compact, model-readable numbered list."""
    if not results:
        return "No results found."
    lines: list[str] = []
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. {r.title}".rstrip())
        if r.url:
            lines.append(f"   {r.url}")
        if r.snippet:
            lines.append(f"   {r.snippet}")
    return "\n".join(lines)


def _clip(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"
    return text
