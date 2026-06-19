"""Lightweight daily diary scheduler.

A single asyncio task that wakes up once a day at the configured ``diary_time``
(local server time) and asks Borb to write his diary entry. No external
scheduling dependency is needed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.agent.diary import write_diary

if TYPE_CHECKING:
    from app.agent.core import AgentCore

log = logging.getLogger("borb.diary")


def parse_time(value: str) -> tuple[int, int]:
    """Parse a ``"HH:MM"`` string into ``(hour, minute)``."""

    hour_str, _, minute_str = value.strip().partition(":")
    hour, minute = int(hour_str), int(minute_str or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid diary_time: {value!r}")
    return hour, minute


def seconds_until(target: str, now: datetime | None = None) -> float:
    """Seconds from ``now`` until the next occurrence of ``HH:MM``."""

    now = now or datetime.now()
    hour, minute = parse_time(target)
    nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


async def run_diary_scheduler(agent: "AgentCore") -> None:
    """Loop forever: sleep until ``diary_time``, write the diary, repeat."""

    diary_time = agent.settings.diary_time
    log.info("Diary scheduler started (daily at %s).", diary_time)
    while True:
        delay = seconds_until(diary_time)
        log.info("Next diary entry in %.0f minutes.", delay / 60)
        await asyncio.sleep(delay)
        try:
            path = await write_diary(agent)
            log.info("Diary entry written: %s", path)
        except asyncio.CancelledError:
            raise
        except Exception:  # never let a bad day kill the scheduler
            log.exception("Failed to write diary entry; will retry tomorrow.")
        # Avoid a tight loop if we woke up a hair early.
        await asyncio.sleep(60)
