"""Manual refresh and explicit native Lovelace dashboard export."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN, CONF_BATTERY_SOC, CONF_PV_POWER, CONF_HOME_POWER,
    CONF_EV_POWER, CONF_HEAT_PUMP_POWER,
)
from .dashboard_export import (
    render_dashboard, render_mini_widget, export_files, FORECAST_CARD_RESOURCE,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_KEYS = (
    "mini_status", "grid_status", "grid_import", "grid_headroom",
    "grid_charge_cap", "grid_phase_status", "grid_reason", "sim_status",
    "sim_soc_end", "sim_soc_min", "sim_soc_min_cautious",
    "sim_pv_kwh", "sim_grid_kwh", "sim_grid_peak", "sim_hours", "sim_quality",
    "tariff", "tariff_zone", "tariff_price", "next_cheap",
    "smart_charge_start", "smart_charge_finish", "smart_charge_power",
    "smart_charge_energy", "smart_charge_target", "dry_run_status",
    "dry_run_action", "dry_run_power", "dry_run_days",
    "accuracy_status", "economic_status", "economic_base_cost",
    "economic_plan_cost", "economic_import_delta",
    "economic_base_export", "economic_plan_export",
    "economic_base_soc", "economic_plan_soc",
    "economic_terminal_delta", "economic_estimate",
    "deye_tou_status", "deye_tou_fields",
    "deye_tou_snapshot", "deye_tou_ready",
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RefreshNowButton(coordinator, entry),
        ExportDashboardButton(coordinator, entry),
    ])


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
        self.coordinator.health.add(
            "info", "MANUAL_REFRESH", "Użytkownik uruchomił odświeżanie")
        self.coordinator.health_store.async_delay_save(
            self.coordinator.health.export, 60)
        await self.coordinator.async_request_refresh()


class ExportDashboardButton(ButtonEntity):
    """On explicit press, export two Lovelace YAML files into HA /config.

    Never auto-adds Lovelace resources, edits existing dashboards, controls
    the inverter, or overwrites an earlier export/user customization.
    """
    _attr_has_entity_name = True
    _attr_name = "Wygeneruj pulpit, miniwidżet i wykres 48h"
    _attr_icon = "mdi:view-dashboard-edit"

    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_dashboard_export"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }
        self._attr_extra_state_attributes = {
            "status": "Nie wygenerowano w tej sesji",
            "adres_zasobu_lovelace": FORECAST_CARD_RESOURCE,
            "wymaga_wklejenia_do_pulpitu": True,
            "nie_modyfikuje_istniejacych_dashboardow": True,
        }

    def _map_entities(self) -> tuple[dict[str, str], dict[str, str]]:
        """Read actual IDs from the Entity Registry; never guess Polish slugs."""
        registry = er.async_get(self.coordinator.hass)
        id_prefix = f"{self.entry.entry_id}_ep20_"
        wanted = {id_prefix + key: key for key in SENSOR_KEYS}
        wanted.update({
            f"{self.entry.entry_id}_health_status": "health_status",
            f"{self.entry.entry_id}_integration_version": "version",
            f"{self.entry.entry_id}_refresh_now": "refresh",
        })
        ids = {}
        for item in registry.entities.values():
            if (item.platform == DOMAIN and
                    item.config_entry_id == self.entry.entry_id and
                    item.disabled_by is None):
                key = wanted.get(item.unique_id)
                if key:
                    ids[key] = item.entity_id

        settings = self.coordinator._selected_settings or {
            **self.entry.data, **self.entry.options,
        }
        mapping = {
            "source_soc": CONF_BATTERY_SOC,
            "source_pv": CONF_PV_POWER,
            "source_home": CONF_HOME_POWER,
            "source_ev": CONF_EV_POWER,
            "source_pump": CONF_HEAT_PUMP_POWER,
        }
        sources = {}
        for key, config_key in mapping.items():
            entity_id = settings.get(config_key)
            # Only display configured sensor IDs, never manufactured names.
            if isinstance(entity_id, str) and entity_id.startswith("sensor."):
                sources[key] = entity_id
        return ids, sources

    async def async_press(self) -> None:
        ids, sources = self._map_entities()
        try:
            script = await self.coordinator.hass.async_add_executor_job(
                Path(__file__).with_name("forecast_card.js").read_text, "utf-8",
            )
            full = render_dashboard(ids, sources)
            mini = render_mini_widget(ids, sources)
            paths = await self.coordinator.hass.async_add_executor_job(
                export_files, self.coordinator.hass.config.path(), full, mini, script,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            self._attr_extra_state_attributes = {
                "status": "Błąd eksportu",
                "przyczyna": str(exc)[:240],
                "wymaga_wklejenia_do_pulpitu": True,
                "nie_modyfikuje_istniejacych_dashboardow": True,
            }
            self.async_write_ha_state()
            raise HomeAssistantError(
                "Nie udało się wygenerować pulpitu ESTADI: " + str(exc)
            ) from exc

        self._attr_extra_state_attributes = {
            "status": "Wygenerowano",
            "pulpit_yaml": paths["dashboard"],
            "miniwidzet_yaml": paths["mini"],
            "karta_js": paths["forecast_js"],
            "adres_zasobu_lovelace": paths["forecast_resource_url"],
            "zarejestruj_zasob_jako": "Moduł JavaScript",
            "liczba_encji_pilota": len(ids),
            "liczba_zewnetrznych_czujnikow": len(sources),
            "wygenerowano_o": datetime.now(timezone.utc).isoformat(),
            "wymaga_wklejenia_do_pulpitu": True,
            "nie_modyfikuje_istniejacych_dashboardow": True,
            "nie_zmieniono_deye": True,
        }
        _LOGGER.info("ESTADI Lovelace export saved: %s", paths)
        self.async_write_ha_state()
