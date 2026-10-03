"""One guarded fetch of buy and sell prices, shared by the refresh button and the website check."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# The API allows 3 requests/hour per endpoint, and the cost sensors already use
# 2 of them on the same path. A refresh within this time of the last fetch is ignored.
REFRESH_GUARD = timedelta(minutes=20)


def price_coordinators(hass, entry_id):
    data = hass.data.get(DOMAIN, {})
    return [
        coordinator
        for coordinator in (data.get(f"{entry_id}_{price_type}") for price_type in ("buy", "sell"))
        if coordinator is not None
    ]


def last_fetch(hass, entry_id):
    fetched = [c.last_price_fetch for c in price_coordinators(hass, entry_id) if c.last_price_fetch]
    return max(fetched) if fetched else None


def refresh_guarded(hass, entry_id) -> bool:
    """True while a refresh would be ignored because the last fetch is too recent."""
    last = last_fetch(hass, entry_id)
    return last is not None and dt_util.utcnow() - last < REFRESH_GUARD


def has_tomorrow(hass, entry_id) -> bool:
    coordinators = price_coordinators(hass, entry_id)
    return bool(coordinators) and all(c._has_tomorrow for c in coordinators)


async def async_refresh_prices(hass, entry_id, reason: str) -> bool:
    """Fetch buy and sell once (one HTTP call, no retries). Returns whether tomorrow is now present."""
    coordinators = price_coordinators(hass, entry_id)
    if not coordinators:
        _LOGGER.warning("Price refresh (%s) skipped: price coordinators are not ready", reason)
        return False

    if refresh_guarded(hass, entry_id):
        _LOGGER.info(
            "Price refresh (%s) ignored: last fetch at %s is less than %d minutes ago",
            reason,
            dt_util.as_local(last_fetch(hass, entry_id)).strftime("%H:%M:%S"),
            int(REFRESH_GUARD.total_seconds() // 60),
        )
        return False

    _LOGGER.info("Refreshing buy and sell prices (%s)", reason)
    # Buy and sell request the same URL; run concurrently, the API client's
    # in-flight dedup turns them into a single HTTP request.
    await asyncio.gather(*(c.async_fetch_once() for c in coordinators))
    return has_tomorrow(hass, entry_id)
