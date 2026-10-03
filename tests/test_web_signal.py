"""Tests for web_signal.py, loaded by path so Home Assistant is not needed.

Fixtures are pstryk.pl/ceny as served on 2026-10-03: at 08:27 CEST (tomorrow not
published, button disabled) and at 12:22 CEST (published, button active).
"""
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
WARSAW = ZoneInfo("Europe/Warsaw")

_spec = importlib.util.spec_from_file_location(
    "web_signal", ROOT / "custom_components" / "pstryk" / "web_signal.py"
)
web_signal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(web_signal)


def _local(*args):
    return datetime(*args, tzinfo=WARSAW)


def test_active_page_is_published():
    html = (FIXTURES / "ceny_active_20261003T1222.html").read_text(encoding="utf-8")
    assert web_signal.next_day_published(html) is True


def test_disabled_page_is_not_published():
    html = (FIXTURES / "ceny_disabled_20261003T0827.html").read_text(encoding="utf-8")
    assert web_signal.next_day_published(html) is False


def test_missing_button_is_none():
    assert web_signal.next_day_published("<html><body>nothing here</body></html>") is None


def test_tailwind_disabled_variant_is_not_the_attribute():
    tag = '<button class="rounded-full disabled:bg-navy-300 bg-primary-100" aria-label="Następny dzień">'
    assert web_signal.next_day_published(tag) is True


@pytest.mark.parametrize("disabled", ['disabled=""', "disabled", 'disabled="disabled"'])
def test_disabled_attribute_forms(disabled):
    tag = f'<button class="bg-navy-300" aria-label="Następny dzień" {disabled}>'
    assert web_signal.next_day_published(tag) is False


@pytest.mark.parametrize(
    "now, expected",
    [
        (_local(2026, 10, 3, 0, 1), _local(2026, 10, 3, 12, 0)),
        (_local(2026, 10, 3, 11, 59, 59), _local(2026, 10, 3, 12, 0)),
        (_local(2026, 10, 3, 12, 0, 0, 5000), _local(2026, 10, 3, 12, 5)),
        (_local(2026, 10, 3, 12, 3), _local(2026, 10, 3, 12, 5)),
        (_local(2026, 10, 3, 13, 50, 0, 1), _local(2026, 10, 3, 13, 55)),
        (_local(2026, 10, 3, 13, 55, 0, 1), _local(2026, 10, 4, 12, 0)),
        (_local(2026, 10, 3, 14, 0), _local(2026, 10, 4, 12, 0)),
        (_local(2026, 10, 3, 23, 59), _local(2026, 10, 4, 12, 0)),
    ],
)
def test_next_web_check(now, expected):
    assert web_signal.next_web_check(now) == expected


def test_window_has_24_checks():
    checks = []
    now = _local(2026, 10, 3, 0, 1)
    while True:
        now = web_signal.next_web_check(now)
        if now.date().day != 3:
            break
        checks.append(now.strftime("%H:%M"))
    assert checks[0] == "12:00"
    assert checks[-1] == "13:55"
    assert len(checks) == 24


def test_dst_change_keeps_local_noon():
    # Clocks go back on 2026-10-25 at 03:00 CEST.
    nxt = web_signal.next_web_check(_local(2026, 10, 24, 15, 0))
    assert (nxt.hour, nxt.minute) == (12, 0)
    assert nxt.utcoffset().total_seconds() == 3600
