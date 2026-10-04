"""Tests for price_policy.py, loaded by path so Home Assistant is not needed."""
import importlib.util
from datetime import datetime
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


def test_cost_skips_the_price_hours():
    allowed = [h for h in range(24) if price_policy.cost_run_allowed(_local(2026, 10, 4, h, 50))]
    assert [h for h in range(24) if h not in allowed] == [11, 12, 13, 23]
