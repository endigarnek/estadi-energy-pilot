"""ESTADI Energy Pilot: advisory PV and home battery optimizer."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta
from pathlib import Path
import logging

from .const import DOMAIN, CONF_EV_TOPOLOGY
from .house_learning import resolve_ev_topology
from .coordinator import EnergyPilotCoordinator

PLATFORMS = ["sensor", "binary_sensor", "button", "number"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Wiring confirmed by the site owner: Deye Load includes EV and heat pump.
    # Migrate old 'unknown' choices without touching deliberately overridden
    # 'excluded' entries. The options are persisted for future restarts.
    stored = entry.options.get(CONF_EV_TOPOLOGY, entry.data.get(CONF_EV_TOPOLOGY))
    chosen = resolve_ev_topology(stored)
    if chosen != stored:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_EV_TOPOLOGY: chosen},
        )
    coordinator = EnergyPilotCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Only installations already activated by an explicit export have a
    # checksum manifest. Keep their managed YAML current after a HACS update
    # without touching manually edited or legacy dashboards.
    await _async_sync_existing_dashboard(hass, entry, coordinator)
    # A periodic watchdog updates the health sensor even if normal polling
    # silently stops; it never sends commands to Deye.
    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda _now: coordinator.async_update_listeners(),
            timedelta(minutes=1),
        )
    )
    # Grid Guard has its own light read-only heartbeat. It must NOT call
    # async_request_refresh(): doing so would repeatedly call Forecast.Solar,
    # pollute historical samples and reset the 15-minute scheduler.
    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda _now: coordinator.refresh_grid_guard_live(),
            timedelta(seconds=15),
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


async def _async_sync_existing_dashboard(hass: HomeAssistant, entry: ConfigEntry,
                                         coordinator: EnergyPilotCoordinator) -> None:
    """Refresh generated YAML after HA restart only when the owner opted in."""
    marker = Path(hass.config.path(".estadi-energy-pilot-managed.json"))
    if not await hass.async_add_executor_job(marker.is_file):
        return
    from .button import ExportDashboardButton

    try:
        _, _, paths = await ExportDashboardButton(
            coordinator, entry
        ).async_generate_managed_files()
    except Exception:
        # UI errors must never interrupt Home Assistant energy monitoring.
        # export_files protects all owner edits with content checksums.
        _LOGGER.exception(
            "Nie odświeżono zarządzanego pulpitu ESTADI; zachowano istniejące pliki"
        )
    else:
        _LOGGER.info("Odświeżono zarządzany pulpit ESTADI po restarcie: %s", paths)
        # Existing managed dashboard is explicit opt-in. Refresh only this
        # module's resource URL; never mutate unrelated Lovelace resources.
        from .lovelace_resource import async_ensure_estadi_resource
        try:
            resource = await async_ensure_estadi_resource(hass)
        except Exception:
            _LOGGER.exception("Nie zaktualizowano zasobu JavaScript ESTADI")
        else:
            _LOGGER.info("Zasób JS ESTADI: %s", resource)
