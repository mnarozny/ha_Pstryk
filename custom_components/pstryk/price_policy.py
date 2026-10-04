"""When the integration may spend API requests: prices first, cost on leftovers.

Pure functions with no Home Assistant imports. Times are local (Europe/Warsaw).
"""
from datetime import datetime, timedelta

# Pstryk publishes tomorrow's prices shortly after 12:00 (seen 2026-10-01 to
# 10-04; on 10-04 the API still had none at 12:00:04).
TOMORROW_EXPECTED_FROM = (12, 5)

# Checks for tomorrow's prices: 12:10, 12:30, 12:50, ... every 20 minutes until
# they are in. Three per hour is the whole hourly budget, so cost waits.
TOMORROW_FIRST_CHECK = (12, 10)
TOMORROW_INTERVAL_MINUTES = 20
TOMORROW_LAST_CHECK = (23, 50)

# Cost runs at :50 only on budget the prices leave free: never while tomorrow's
# prices are missing after 12:00, never at 11:50 (its requests would still count
# against the 12:10-12:50 checks) or 23:50 (the 00:01 fetch).
COST_RUN_MINUTE = 50
COST_SKIP_HOURS = frozenset({11, 23})
COST_KEEP_FREE = 1


def startup_fetch_needed(today_hours: int, has_tomorrow: bool, now: datetime) -> bool:
    """Whether a start-up needs the API, given what the price cache holds."""
    if today_hours < 20:
        return True
    return not has_tomorrow and (now.hour, now.minute) >= TOMORROW_EXPECTED_FROM


def next_tomorrow_check(now: datetime) -> datetime:
    """The next check for tomorrow's prices strictly after `now`."""
    first = now.replace(hour=TOMORROW_FIRST_CHECK[0], minute=TOMORROW_FIRST_CHECK[1], second=0, microsecond=0)
    last = now.replace(hour=TOMORROW_LAST_CHECK[0], minute=TOMORROW_LAST_CHECK[1], second=0, microsecond=0)
    if now < first:
        return first
    minutes_since_first = int((now - first).total_seconds() // 60)
    check = first + timedelta(
        minutes=(minutes_since_first // TOMORROW_INTERVAL_MINUTES + 1) * TOMORROW_INTERVAL_MINUTES
    )
    if check <= last:
        return check
    return (now + timedelta(days=1)).replace(
        hour=TOMORROW_FIRST_CHECK[0], minute=TOMORROW_FIRST_CHECK[1], second=0, microsecond=0
    )


def next_cost_run(now: datetime) -> datetime:
    """The next :50 strictly after `now`."""
    run = now.replace(minute=COST_RUN_MINUTE, second=0, microsecond=0)
    if run <= now:
        run = (now + timedelta(hours=1)).replace(minute=COST_RUN_MINUTE, second=0, microsecond=0)
    return run


def cost_run_allowed(now: datetime, has_tomorrow: bool) -> bool:
    if now.hour in COST_SKIP_HOURS:
        return False
    return has_tomorrow or now.hour < 12
