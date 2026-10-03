import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .price_refresh import async_refresh_prices
from .sensor import get_integration_version

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    async_add_entities([PstrykRefreshPricesButton(entry.entry_id)])


class PstrykRefreshPricesButton(ButtonEntity):
    """Fetch buy and sell prices once. Ignored within 20 minutes of the last fetch."""

    _attr_icon = "mdi:refresh"

    def __init__(self, entry_id: str):
        self.entry_id = entry_id
        self.entity_id = f"button.{DOMAIN}_refresh_prices"

    @property
    def name(self) -> str:
        return "Pstryk Refresh Prices"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_refresh_prices"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "pstryk_energy")},
            "name": "Pstryk Energy",
            "manufacturer": "Pstryk",
            "model": "Energy Price Monitor",
            "sw_version": get_integration_version(self.hass),
        }

    async def async_press(self) -> None:
        # Coordinators are created by the sensor platform, so look them up at press time.
        await async_refresh_prices(self.hass, self.entry_id, "button")
