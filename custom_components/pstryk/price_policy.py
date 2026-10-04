"""When the integration may spend API requests: prices first, cost on leftovers.

Pure functions with no Home Assistant imports. Times are local (Europe/Warsaw).
"""
from datetime import datetime, timedelta

# Pstryk publishes tomorrow's prices shortly after 12:00.
TOMORROW_EXPECTED_FROM = (12, 5)

# Cost runs at :50, after the hour's price traffic, and only if its calls
# leave a slot free. It skips the hours whose next 60 minutes hold price
# fetches: the pstryk.pl check (12:00-13:55), the 14:00-15:00 checks and 00:01.
COST_RUN_MINUTE = 50
COST_SKIP_HOURS = frozenset({11, 12, 13, 23})
COST_KEEP_FREE = 1


def startup_fetch_needed(today_hours: int, has_tomorrow: bool, now: datetime) -> bool:
    """Whether a start-up needs the API, given what the price cache holds."""
    if today_hours < 20:
        return True
    return not has_tomorrow and (now.hour, now.minute) >= TOMORROW_EXPECTED_FROM


def next_cost_run(now: datetime) -> datetime:
    """The next :50 strictly after `now`."""
    run = now.replace(minute=COST_RUN_MINUTE, second=0, microsecond=0)
    if run <= now:
        run = (now + timedelta(hours=1)).replace(minute=COST_RUN_MINUTE, second=0, microsecond=0)
    return run


def cost_run_allowed(now: datetime) -> bool:
    return now.hour not in COST_SKIP_HOURS
