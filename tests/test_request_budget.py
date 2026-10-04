"""Tests for request_budget.py, loaded by path so Home Assistant is not needed."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "request_budget", ROOT / "custom_components" / "pstryk" / "request_budget.py"
)
request_budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(request_budget)
RequestBudget = request_budget.RequestBudget


def _utc(hour, minute, second=0):
    # 2026-10-04 in UTC; 10:05Z is 12:05 CEST.
    return datetime(2026, 10, 4, hour, minute, second, tzinfo=timezone.utc)


def test_review_sequence_has_no_room_for_a_fourth_request():
    # Start-up price fetch, then two cost fetches 15 s later (review of PR #3).
    budget = RequestBudget(3)
    assert budget.claim(_utc(10, 5, 0))
    assert budget.claim(_utc(10, 5, 15))
    assert budget.claim(_utc(10, 5, 15))
    assert not budget.has_room(_utc(10, 25, 5))
    assert not budget.claim(_utc(10, 25, 5))
    assert budget.used(_utc(10, 25, 5)) == 3
    assert budget.free_at(_utc(10, 25, 5)) == _utc(11, 5, 0)


def test_slots_free_after_exactly_one_hour():
    budget = RequestBudget(3)
    for second in (0, 15, 15):
        budget.claim(_utc(10, 5, second))
    assert not budget.has_room(_utc(11, 4, 59))
    assert budget.has_room(_utc(11, 5, 0))
    assert budget.used(_utc(11, 5, 0)) == 2


def test_keep_free_leaves_slots_for_prices():
    budget = RequestBudget(3)
    now = _utc(13, 50)
    assert budget.claim(now, keep_free=1)
    assert budget.claim(now, keep_free=1)
    assert not budget.claim(now, keep_free=1)  # the last slot stays for prices
    assert budget.claim(now)  # a price request may take it
    assert budget.free_at(now, keep_free=1) == now + timedelta(hours=1)


def test_block_after_429():
    budget = RequestBudget(3)
    budget.block_until(_utc(11, 0))
    assert not budget.has_room(_utc(10, 30))
    assert budget.free_at(_utc(10, 30)) == _utc(11, 0)
    assert budget.has_room(_utc(11, 0))


def test_persistence_round_trip_drops_old_entries():
    budget = RequestBudget(3)
    budget.claim(_utc(9, 0))
    budget.claim(_utc(10, 30))
    budget.block_until(_utc(10, 45))
    data = budget.to_dict(_utc(10, 40))
    assert data == {
        "times": [_utc(10, 30).isoformat()],
        "blocked_until": _utc(10, 45).isoformat(),
    }
    restored = RequestBudget.from_dict(data, 3)
    assert restored.used(_utc(10, 40)) == 1
    assert not restored.has_room(_utc(10, 41))


def test_damaged_log_counts_from_empty():
    restored = RequestBudget.from_dict({"times": ["not a time"]}, 3)
    assert restored.used(_utc(10, 0)) == 0
