"""API budget, price refresh, button and website check, with stand-ins for Home Assistant.

Home Assistant is not installed here, so the HA names these modules import are
replaced by small stubs (as in tests/test_json_entries.py on the price-components
branch). The real API client, coordinators, refresh, button and watcher run
against a fake HTTP session that records when each request is sent.

The clock is local Europe/Warsaw. The fixture was fetched on 2026-10-02 at 12:05,
so 2026-10-02 afternoon has both days published.
"""
import asyncio
import copy
import importlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "pstryk"
FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("Europe/Warsaw")
CLOCK = [datetime(2026, 10, 2, 12, 5, tzinfo=TZ)]
PRICING = json.loads((FIXTURES / "api_pricing_20261002T120545.json").read_text())

STORE_DISK = {}  # survives "restarts": one dict per store key
SCHEDULED = []  # (when_utc, callback) from async_track_point_in_time
NOTIFICATIONS = {}


def _set_clock(*args):
    CLOCK[0] = datetime(*args, tzinfo=TZ)


def _as_local(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.astimezone(TZ)


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class _Coordinator:
    def __init__(self, hass, logger, name=None, **kwargs):
        self.hass, self.name, self.data, self.last_update_success = hass, name, None, True

    def async_update_listeners(self):
        pass

    def async_set_updated_data(self, data):
        self.data, self.last_update_success = data, True

    async def async_request_refresh(self):
        try:
            self.data = await self._async_update_data()
            self.last_update_success = True
        except Exception:
            self.last_update_success = False


class _Store:
    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return copy.deepcopy(STORE_DISK.get(self.key))

    async def async_save(self, data):
        STORE_DISK[self.key] = copy.deepcopy(data)


def _track(hass, callback, when):
    item = (when, callback)
    SCHEDULED.append(item)
    return lambda: SCHEDULED.remove(item) if item in SCHEDULED else None


def _stub(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def _stubs():
    dt = _stub(
        "homeassistant.util.dt",
        now=lambda: CLOCK[0],
        utcnow=lambda: CLOCK[0].astimezone(timezone.utc),
        as_utc=lambda d: d.astimezone(timezone.utc),
        as_local=_as_local,
        parse_datetime=_parse_datetime,
        DEFAULT_TIME_ZONE=TZ,
    )
    aiohttp = _stub("aiohttp")
    aiohttp.__getattr__ = lambda name: type(name, (Exception,), {})
    notify = _stub(
        "homeassistant.components.persistent_notification",
        async_create=lambda hass, message, title=None, notification_id=None: NOTIFICATIONS.__setitem__(
            notification_id, message
        ),
        async_dismiss=lambda hass, notification_id: NOTIFICATIONS.pop(notification_id, None),
    )
    package = _stub("pstryk")
    package.__path__ = [str(PKG)]
    return {
        "homeassistant": _stub("homeassistant"),
        "homeassistant.util": _stub("homeassistant.util", dt=dt),
        "homeassistant.util.dt": dt,
        "homeassistant.helpers": _stub("homeassistant.helpers"),
        "homeassistant.helpers.update_coordinator": _stub(
            "homeassistant.helpers.update_coordinator",
            DataUpdateCoordinator=_Coordinator,
            UpdateFailed=type("UpdateFailed", (Exception,), {}),
            CoordinatorEntity=type("CoordinatorEntity", (), {"__init__": lambda self, c: None}),
        ),
        "homeassistant.helpers.event": _stub("homeassistant.helpers.event", async_track_point_in_time=_track),
        "homeassistant.helpers.storage": _stub("homeassistant.helpers.storage", Store=_Store),
        "homeassistant.helpers.restore_state": _stub(
            "homeassistant.helpers.restore_state", RestoreEntity=type("RestoreEntity", (), {})
        ),
        "homeassistant.helpers.aiohttp_client": _stub(
            "homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: hass.session
        ),
        "homeassistant.config_entries": _stub(
            "homeassistant.config_entries", ConfigEntry=type("ConfigEntry", (), {})
        ),
        "homeassistant.core": _stub(
            "homeassistant.core", HomeAssistant=type("HomeAssistant", (), {}), callback=lambda f: f
        ),
        "homeassistant.components": _stub("homeassistant.components", persistent_notification=notify),
        "homeassistant.components.persistent_notification": notify,
        "homeassistant.components.button": _stub(
            "homeassistant.components.button", ButtonEntity=type("ButtonEntity", (), {})
        ),
        "homeassistant.components.sensor": _stub(
            "homeassistant.components.sensor",
            SensorEntity=type("SensorEntity", (), {}),
            SensorStateClass=types.SimpleNamespace(MEASUREMENT="measurement", TOTAL="total"),
            SensorDeviceClass=types.SimpleNamespace(MONETARY="monetary"),
        ),
        "homeassistant.loader": _stub("homeassistant.loader", async_get_integration=None),
        "aiohttp": aiohttp,
        "pstryk": package,
    }


@pytest.fixture(scope="module")
def mods():
    stubs = _stubs()
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        yield types.SimpleNamespace(
            api=importlib.import_module("pstryk.api_client"),
            uc=importlib.import_module("pstryk.update_coordinator"),
            cost=importlib.import_module("pstryk.energy_cost_coordinator"),
            refresh=importlib.import_module("pstryk.price_refresh"),
            watch=importlib.import_module("pstryk.web_watch"),
            button=importlib.import_module("pstryk.button"),
        )
    finally:
        for name in [n for n in sys.modules if n == "pstryk" or n.startswith("pstryk.")]:
            del sys.modules[name]
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class _Response:
    def __init__(self, status, body):
        self.status, self._body, self.headers = status, body, {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return copy.deepcopy(self._body)

    async def text(self):
        return "error"


class _Session:
    """Records the time of every HTTP request; serves queued statuses, then 200."""

    def __init__(self):
        self.sent = []
        self.statuses = []

    def get(self, url, headers=None):
        self.sent.append(CLOCK[0])
        status = self.statuses.pop(0) if self.statuses else 200
        body = PRICING if "metrics=pricing" in url else {"frames": []}
        return _Response(status, body)

    def max_in_any_hour(self):
        return max(
            (sum(1 for t in self.sent if s <= t < s + timedelta(hours=1)) for s in self.sent),
            default=0,
        )


class _Hass:
    def __init__(self):
        self.session = _Session()
        self.data = {"pstryk": {}}


@pytest.fixture
def env(mods):
    STORE_DISK.clear()
    SCHEDULED.clear()
    NOTIFICATIONS.clear()
    _set_clock(2026, 10, 2, 12, 5)
    hass = _Hass()

    async def build():
        client = mods.api.PstrykAPIClient(hass, "key", "e")
        await client.async_load_budget()
        client._calculate_backoff = lambda attempt, base_delay=20.0: 0
        coords = {}
        for price_type in ("buy", "sell"):
            coord = mods.uc.PstrykDataUpdateCoordinator(hass, client, price_type, False, 5, 30, "e")

            async def _no_cache_write(data):
                return None

            coord._save_cache = _no_cache_write
            hass.data["pstryk"][f"e_{price_type}"] = coord
            coords[price_type] = coord
        return client, coords

    return types.SimpleNamespace(hass=hass, build=build)


def _run(coro):
    return asyncio.run(coro)


async def _two_more_calls(client):
    # Stand-in for any other traffic on the shared endpoint (e.g. cost).
    url = "https://api.pstryk.pl/integrations/meter-data/unified-metrics/?metrics=meter_values,cost"
    await client.fetch(url, max_retries=1)
    await client.fetch(url, max_retries=1)


def test_review_p1_refresh_waits_for_the_shared_budget(mods, env):
    async def scenario():
        client, coords = await env.build()
        await asyncio.gather(*(c.async_request_refresh() for c in coords.values()))  # 12:05:00, one request
        _set_clock(2026, 10, 2, 12, 5, 15)
        await _two_more_calls(client)
        _set_clock(2026, 10, 2, 12, 25, 5)
        blocked = await mods.refresh.async_refresh_prices(env.hass, "e", "test")
        sent_when_blocked = len(env.hass.session.sent)
        _set_clock(2026, 10, 2, 13, 5, 1)
        allowed = await mods.refresh.async_refresh_prices(env.hass, "e", "test")
        return blocked, sent_when_blocked, allowed

    blocked, sent_when_blocked, allowed = _run(scenario())
    assert blocked == "budget"
    assert sent_when_blocked == 3
    assert allowed == "found"
    assert len(env.hass.session.sent) == 4
    assert env.hass.session.max_in_any_hour() == 3


def test_budget_survives_a_restart(mods, env):
    async def scenario():
        client, coords = await env.build()
        await asyncio.gather(*(c.async_request_refresh() for c in coords.values()))
        await _two_more_calls(client)
        _set_clock(2026, 10, 2, 12, 30)
        env.hass.data["pstryk"].clear()
        await env.build()  # restart: a new client loads the saved request log
        return await mods.refresh.async_refresh_prices(env.hass, "e", "after restart")

    assert _run(scenario()) == "budget"
    assert len(env.hass.session.sent) == 3


def test_review_p2_concurrent_refreshes_keep_retries(mods, env):
    async def scenario():
        client, coords = await env.build()
        seen = []
        original = client._make_request

        async def spy(url, max_retries=3, base_delay=20.0, keep_free=0):
            seen.append(max_retries)
            return await original(url, max_retries, base_delay, keep_free)

        client._make_request = spy
        results = await asyncio.gather(
            mods.refresh.async_refresh_prices(env.hass, "e", "press 1"),
            mods.refresh.async_refresh_prices(env.hass, "e", "press 2"),
        )
        _set_clock(2026, 10, 2, 14, 0)
        await coords["buy"]._async_update_data()  # an ordinary scheduled fetch
        return results, seen, [c.retry_attempts for c in coords.values()]

    results, seen, retry_attempts = _run(scenario())
    assert results == ["found", "found"]
    assert retry_attempts == [5, 5]
    assert seen[-1] == 5
    assert all(r == 1 for r in seen[:-1])
    # Two presses ran one after the other; each one request (buy and sell deduplicated).
    assert len(env.hass.session.sent) == 3


def test_retries_count_and_stop_at_the_budget(mods, env):
    async def scenario():
        client, coords = await env.build()
        coords["buy"].data = {"prices": [], "kept": True}
        env.hass.session.statuses = [500, 500, 500, 500, 500]
        await coords["buy"].async_request_refresh()
        return coords["buy"]

    buy = _run(scenario())
    assert len(env.hass.session.sent) == 3  # 5 retries configured, budget allows 3
    assert buy.data == {"prices": [], "kept": True}  # current data kept
    assert buy.last_update_success is True
    assert buy._unsub_budget_retry is not None  # a fetch is booked for when a slot frees
    assert SCHEDULED[-1][0] == datetime(2026, 10, 2, 13, 5, 5, tzinfo=TZ).astimezone(timezone.utc)


def test_cost_runs_only_on_leftover_budget(mods, env):
    async def scenario():
        client, coords = await env.build()
        cost = mods.cost.PstrykCostDataUpdateCoordinator(env.hass, client, 5, 30)
        cost.schedule_hourly_update = lambda: None
        _set_clock(2026, 10, 2, 12, 50)
        await cost._handle_hourly_update(None)  # price hours: skipped
        at_1250 = len(env.hass.session.sent)
        _set_clock(2026, 10, 2, 15, 50)
        await cost._handle_hourly_update(None)  # empty budget: daily + yearly
        at_1550 = len(env.hass.session.sent)
        _set_clock(2026, 10, 2, 16, 20)
        await cost._handle_hourly_update(None)  # 2 used: the last slot stays for prices
        at_1620 = len(env.hass.session.sent)
        price = await mods.refresh.async_refresh_prices(env.hass, "e", "after cost")
        return at_1250, at_1550, at_1620, price

    at_1250, at_1550, at_1620, price = _run(scenario())
    assert (at_1250, at_1550, at_1620) == (0, 2, 2)
    assert price == "found"
    assert env.hass.session.max_in_any_hour() == 3


def test_button_reports_a_full_budget(mods, env):
    async def scenario():
        client, coords = await env.build()
        await _two_more_calls(client)
        await client.fetch(
            "https://api.pstryk.pl/integrations/meter-data/unified-metrics/?metrics=cost", max_retries=1
        )
        button = mods.button.PstrykRefreshPricesButton("e")
        button.hass = env.hass
        await button.async_press()

    _run(scenario())
    assert len(env.hass.session.sent) == 3
    assert "13:05" in NOTIFICATIONS["pstryk_refresh_budget"]


def test_watcher_waits_for_budget_then_fetches_once(mods, env):
    async def scenario():
        client, coords = await env.build()
        await _two_more_calls(client)
        await client.fetch(
            "https://api.pstryk.pl/integrations/meter-data/unified-metrics/?metrics=cost", max_retries=1
        )
        watcher = mods.watch.PstrykWebSignalWatcher(env.hass, "e", "test")

        async def published():
            return True

        watcher._fetch_signal = published
        _set_clock(2026, 10, 2, 12, 10)
        await watcher._check()
        waiting = watcher._done_date
        _set_clock(2026, 10, 2, 13, 10)
        await watcher._check()
        return waiting, watcher._done_date

    waiting, done = _run(scenario())
    assert waiting is None  # budget full: not given up
    assert done == datetime(2026, 10, 2, tzinfo=TZ).date()
    assert len(env.hass.session.sent) == 4
    assert env.hass.session.max_in_any_hour() == 3
