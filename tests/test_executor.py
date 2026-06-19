"""Tests for the system execution layer's shell handling.

Regression coverage for the Windows ``SelectorEventLoop`` issue where
``asyncio.create_subprocess_shell`` raised ``NotImplementedError``. The executor
now runs commands via a blocking ``subprocess.run`` offloaded to a worker
thread, which works on every platform regardless of event loop policy.
"""

import sys

import pytest

from app.config import Settings
from app.schemas import ActionType, ShellAction, WebsearchAction
from app.system.executor import SystemExecutor
from app.system.websearch.base import SearchResult, WebsearchProviderBase


def _executor(**overrides) -> SystemExecutor:
    settings = Settings(**overrides)
    return SystemExecutor(settings)


class FakeWebsearchProvider(WebsearchProviderBase):
    name = "fake"

    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error
        self.calls = []

    async def search(self, query, max_results=5):
        self.calls.append((query, max_results))
        if self._error is not None:
            raise self._error
        return self._results


@pytest.mark.asyncio
async def test_run_shell_captures_stdout_and_exit_code():
    executor = _executor()
    action = ShellAction(command=f'{sys.executable} -c "print(\'hello borb\')"')

    result = await executor.execute(action)

    assert result.type == ActionType.SHELL
    assert result.status == "executed"
    assert result.exit_code == 0
    assert "hello borb" in (result.stdout or "")


@pytest.mark.asyncio
async def test_run_shell_captures_nonzero_exit():
    executor = _executor()
    action = ShellAction(command=f'{sys.executable} -c "import sys; sys.exit(3)"')

    result = await executor.execute(action)

    assert result.status == "executed"
    assert result.exit_code == 3


@pytest.mark.asyncio
async def test_run_shell_times_out():
    executor = _executor(shell_timeout=1)
    action = ShellAction(command=f'{sys.executable} -c "import time; time.sleep(5)"')

    result = await executor.execute(action)

    assert result.status == "error"
    assert "timed out" in (result.error or "")


@pytest.mark.asyncio
async def test_run_websearch_formats_results():
    provider = FakeWebsearchProvider(
        results=[
            SearchResult(
                title="Python 3.13", url="https://example.com/py", snippet="new release"
            )
        ]
    )
    executor = SystemExecutor(Settings(websearch_max_results=3), websearch=provider)
    action = WebsearchAction(query="python release", intent="check version")

    result = await executor.execute(action)

    assert result.type == ActionType.WEBSEARCH
    assert result.status == "executed"
    assert result.query == "python release"
    assert "Python 3.13" in (result.output or "")
    assert "https://example.com/py" in (result.output or "")
    # The configured default is used when the action omits max_results.
    assert provider.calls == [("python release", 3)]


@pytest.mark.asyncio
async def test_run_websearch_respects_action_max_results():
    provider = FakeWebsearchProvider(results=[])
    executor = SystemExecutor(Settings(websearch_max_results=5), websearch=provider)

    result = await executor.execute(WebsearchAction(query="q", max_results=2))

    assert result.status == "executed"
    assert provider.calls == [("q", 2)]


@pytest.mark.asyncio
async def test_run_websearch_surfaces_errors_as_result():
    provider = FakeWebsearchProvider(error=RuntimeError("rate limited"))
    executor = SystemExecutor(Settings(), websearch=provider)

    result = await executor.execute(WebsearchAction(query="q"))

    assert result.status == "error"
    assert "rate limited" in (result.error or "")
