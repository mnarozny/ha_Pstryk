"""Detect on pstryk.pl whether tomorrow's prices are published.

Pure functions with no Home Assistant imports, so they can be tested with plain
pytest. The watcher that uses them lives in web_watch.py.
"""
import re
from datetime import datetime, timedelta

WINDOW_START_HOUR = 12
WINDOW_END_HOUR = 14
INTERVAL_MINUTES = 5

# pstryk.pl/ceny renders the "next day" arrow server-side. It carries the
# disabled attribute until tomorrow's prices are out. The class list also
# contains Tailwind variants such as "disabled:bg-navy-300", hence the lookahead.
_NEXT_DAY_BUTTON = re.compile(r'<button\b[^>]*aria-label="Następny dzień"[^>]*>')
_DISABLED_ATTR = re.compile(r'\sdisabled(?=[\s=/>])')


def next_day_published(html: str) -> bool | None:
    """True if the next-day button is active, False if disabled, None if not found."""
    match = _NEXT_DAY_BUTTON.search(html)
    if match is None:
        return None
    return _DISABLED_ATTR.search(match.group(0)) is None


def next_web_check(now: datetime) -> datetime:
    """Next check strictly after `now`: every 5 min from 12:00 to 13:55 local, else 12:00 the next day."""
    first_check = now.replace(hour=WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    window_end = now.replace(hour=WINDOW_END_HOUR, minute=0, second=0, microsecond=0)

    if now < first_check:
        return first_check

    minutes_since_first = int((now - first_check).total_seconds() // 60)
    next_check = first_check + timedelta(
        minutes=(minutes_since_first // INTERVAL_MINUTES + 1) * INTERVAL_MINUTES
    )
    if next_check < window_end:
        return next_check

    return (now + timedelta(days=1)).replace(
        hour=WINDOW_START_HOUR, minute=0, second=0, microsecond=0
    )
