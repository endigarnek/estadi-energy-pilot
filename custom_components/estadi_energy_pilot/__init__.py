"""ESTADI Energy Pilot: advisory PV and home battery optimizer."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .const import DOMAIN
from .coordinator import EnergyPilotCoordinator

PLATFORMS = ["sensor", "binary_sensor", "button", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EnergyPilotCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # A periodic watchdog updates the health sensor even if normal polling
    # silently stops; it never sends commands to Deye.
    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda _now: coordinator.async_update_listeners(),
            timedelta(minutes=1),
        )
    )
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return success


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply edited tuning immediately without reloading the integration."""
    await hass.data[DOMAIN][entry.entry_id].async_request_refresh()
