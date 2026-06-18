"""Tests for the system execution layer's shell handling.

Regression coverage for the Windows ``SelectorEventLoop`` issue where
``asyncio.create_subprocess_shell`` raised ``NotImplementedError``. The executor
now runs commands via a blocking ``subprocess.run`` offloaded to a worker
thread, which works on every platform regardless of event loop policy.
"""

import sys

import pytest

from app.config import Settings
from app.schemas import ActionType, ShellAction
from app.system.executor import SystemExecutor


def _executor(**overrides) -> SystemExecutor:
    settings = Settings(**overrides)
    return SystemExecutor(settings)


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
