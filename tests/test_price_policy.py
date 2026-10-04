"""Tests for price_policy.py, loaded by path so Home Assistant is not needed."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
WARSAW = ZoneInfo("Europe/Warsaw")
_spec = importlib.util.spec_from_file_location(
    "price_policy", ROOT / "custom_components" / "pstryk" / "price_policy.py"
)
price_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(price_policy)


def _local(*args):
    return datetime(*args, tzinfo=WARSAW)


@pytest.mark.parametrize(
    "today_hours, has_tomorrow, now, expected",
    [
        (0, False, _local(2026, 10, 4, 9, 0), True),  # empty or stale cache
        (12, False, _local(2026, 10, 4, 9, 0), True),  # partial day
        (24, False, _local(2026, 10, 4, 11, 0), False),  # tomorrow not due yet
        (24, False, _local(2026, 10, 4, 12, 4), False),
        (24, False, _local(2026, 10, 4, 12, 5), True),  # tomorrow due, missing
        (24, False, _local(2026, 10, 4, 12, 30), True),
        (24, True, _local(2026, 10, 4, 12, 30), False),  # complete cache
        (23, True, _local(2026, 10, 25, 20, 0), False),  # DST day has 25 hours, 23 is enough
    ],
)
def test_startup_fetch_needed(today_hours, has_tomorrow, now, expected):
    assert price_policy.startup_fetch_needed(today_hours, has_tomorrow, now) is expected


@pytest.mark.parametrize(
    "now, expected",
    [
        (_local(2026, 10, 4, 9, 0), _local(2026, 10, 4, 9, 50)),
        (_local(2026, 10, 4, 9, 49, 59), _local(2026, 10, 4, 9, 50)),
        (_local(2026, 10, 4, 9, 50), _local(2026, 10, 4, 10, 50)),
        (_local(2026, 10, 4, 23, 55), _local(2026, 10, 5, 0, 50)),
    ],
)
def test_next_cost_run(now, expected):
    assert price_policy.next_cost_run(now) == expected


def test_cost_waits_for_tomorrows_prices():
    def skipped(has_tomorrow):
        return [h for h in range(24) if not price_policy.cost_run_allowed(_local(2026, 10, 4, h, 50), has_tomorrow)]

    assert skipped(True) == [11, 23]
    assert skipped(False) == [11] + list(range(12, 24))


@pytest.mark.parametrize(
    "now, expected",
    [
        (_local(2026, 10, 4, 0, 1), _local(2026, 10, 4, 12, 10)),
        (_local(2026, 10, 4, 12, 0, 4), _local(2026, 10, 4, 12, 10)),
        (_local(2026, 10, 4, 12, 10, 0, 5000), _local(2026, 10, 4, 12, 30)),
        (_local(2026, 10, 4, 12, 31), _local(2026, 10, 4, 12, 50)),
        (_local(2026, 10, 4, 12, 50, 1), _local(2026, 10, 4, 13, 10)),
        (_local(2026, 10, 4, 23, 30, 1), _local(2026, 10, 4, 23, 50)),
        (_local(2026, 10, 4, 23, 50, 1), _local(2026, 10, 5, 12, 10)),
    ],
)
def test_next_tomorrow_check(now, expected):
    assert price_policy.next_tomorrow_check(now) == expected


def test_tomorrow_checks_fit_the_hourly_budget():
    checks, now = [], _local(2026, 10, 4, 0, 1)
    while True:
        now = price_policy.next_tomorrow_check(now)
        if now.day != 4:
            break
        checks.append(now)
    assert checks[:3] == [_local(2026, 10, 4, 12, m) for m in (10, 30, 50)]
    assert max(sum(1 for c in checks if s <= c < s + timedelta(hours=1)) for s in checks) == 3


def test_dst_change_keeps_local_check_times():
    nxt = price_policy.next_tomorrow_check(_local(2026, 10, 24, 23, 55))
    assert (nxt.day, nxt.hour, nxt.minute) == (25, 12, 10)
    assert nxt.utcoffset().total_seconds() == 3600
