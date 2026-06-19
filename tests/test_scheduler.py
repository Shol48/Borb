from datetime import datetime

import pytest

from app.agent.scheduler import parse_time, seconds_until


def test_parse_time():
    assert parse_time("21:00") == (21, 0)
    assert parse_time("9:5") == (9, 5)


def test_parse_time_rejects_invalid():
    with pytest.raises(ValueError):
        parse_time("25:00")


def test_seconds_until_later_today():
    now = datetime(2026, 6, 19, 20, 0, 0)
    assert seconds_until("21:00", now) == 3600


def test_seconds_until_rolls_to_next_day():
    now = datetime(2026, 6, 19, 22, 0, 0)
    # 23 hours until 21:00 the next day
    assert seconds_until("21:00", now) == 23 * 3600
