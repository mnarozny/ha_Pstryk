"""Experimental: watch pstryk.pl for tomorrow's prices and fetch them once when they appear.

From 12:00 to 13:55 local, every 5 minutes, while tomorrow's prices are missing.
When the next-day button turns active, one price fetch follows, if the hourly
API budget has room; otherwise it is tried again at the next check. Anything
unexpected (page unreachable, button gone, fetch without tomorrow) ends the
check for the day; the regular schedule (14:00 in 48h mode, 00:01) still runs.
"""
import asyncio
import logging

import aiohttp
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import WEB_SIGNAL_URL
from .price_refresh import async_refresh_prices, has_tomorrow
from .web_signal import next_day_published, next_web_check

_LOGGER = logging.getLogger(__name__)

PAGE_TIMEOUT = 20


class PstrykWebSignalWatcher:

    def __init__(self, hass, entry_id, version):
        self.hass = hass
        self.entry_id = entry_id
        self._user_agent = f"ha_Pstryk/{version} (+https://github.com/mnarozny/ha_Pstryk)"
        self._unsub = None
        self._stopped = False
        self._done_date = None

    @callback
    def start(self):
        self._schedule()

    @callback
    def stop(self):
        self._stopped = True
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _schedule(self):
        if self._stopped:
            return
        next_check = next_web_check(dt_util.now())
        _LOGGER.debug("Next pstryk.pl check at %s", next_check.strftime("%Y-%m-%d %H:%M:%S"))
        self._unsub = async_track_point_in_time(
            self.hass, self._handle_check, dt_util.as_utc(next_check)
        )

    async def _handle_check(self, _):
        self._unsub = None
        try:
            await self._check()
        except Exception:
            _LOGGER.exception("pstryk.pl check failed")
        finally:
            self._schedule()

    async def _check(self):
        today = dt_util.now().date()
        if self._done_date == today:
            return

        if has_tomorrow(self.hass, self.entry_id):
            _LOGGER.debug("Tomorrow's prices already present, pstryk.pl check done for today")
            self._done_date = today
            return

        published = await self._fetch_signal()
        if published is None:
            self._done_date = today
            return
        if not published:
            _LOGGER.debug("Tomorrow's prices not on pstryk.pl yet")
            return

        _LOGGER.info("Tomorrow's prices are on pstryk.pl, fetching them once")
        result = await async_refresh_prices(self.hass, self.entry_id, "pstryk.pl signal")
        if result == "budget":
            # Nothing was sent; try again at the next check.
            return

        self._done_date = today
        if result == "found":
            _LOGGER.info("Found tomorrow prices after the pstryk.pl signal")
        else:
            _LOGGER.warning(
                "pstryk.pl showed tomorrow's prices but the fetch did not return them (%s); "
                "waiting for the regular schedule", result
            )

    async def _fetch_signal(self):
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(PAGE_TIMEOUT):
                async with session.get(WEB_SIGNAL_URL, headers={"User-Agent": self._user_agent}) as response:
                    if response.status != 200:
                        _LOGGER.warning(
                            "pstryk.pl returned HTTP %d; website check off for today", response.status
                        )
                        return None
                    html = await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Could not load pstryk.pl (%s); website check off for today", err)
            return None

        published = next_day_published(html)
        if published is None:
            _LOGGER.warning(
                "Next-day button not found on pstryk.pl, the page may have changed; "
                "website check off for today"
            )
        return published
