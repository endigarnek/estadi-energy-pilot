"""Manual refresh, visible in the Home Assistant device page."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([RefreshNowButton(hass.data[DOMAIN][entry.entry_id], entry)])


class RefreshNowButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Odśwież teraz"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_refresh_now"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }

    async def async_press(self):
        await self.coordinator.async_request_refresh()
