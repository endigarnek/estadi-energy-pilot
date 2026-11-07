"""Manual refresh and explicit native Lovelace dashboard export."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN, CONF_BATTERY_SOC, CONF_BATTERY_POWER, CONF_PV_POWER, CONF_HOME_POWER,
    CONF_EV_POWER, CONF_HEAT_PUMP_POWER,
)
from .dashboard_export import (
    render_dashboard, render_mini_widget, export_files, FORECAST_CARD_RESOURCE,
)
from .lab_checks import DIAGNOSTIC_TESTS, inspect_test

_LOGGER = logging.getLogger(__name__)

SENSOR_KEYS = (
    "mini_status", "history_status", "lab_status", "grid_status", "grid_import", "grid_raw_power", "grid_raw_status", "grid_limit", "grid_headroom",
    "grid_charge_cap", "grid_phase_status", "grid_reason", "sim_status",
    "sim_soc_end", "sim_soc_min", "sim_soc_min_cautious",
    "sim_pv_kwh", "sim_grid_kwh", "sim_grid_peak", "sim_hours", "sim_quality",
    "tariff", "tariff_zone", "tariff_price", "next_cheap",
    "smart_charge_status", "smart_charge_start", "smart_charge_finish", "smart_charge_power",
    "smart_charge_energy", "smart_charge_target", "dry_run_status",
    "dry_run_action", "dry_run_power", "dry_run_days",
    "accuracy_status", "economic_status", "economic_base_cost",
    "economic_plan_cost", "economic_import_delta",
    "pump_excess_status", "pump_excess_hours", "pump_excess_events",
    "pump_excess_kwh", "pump_excess_last",
    "pump_learn_status", "pump_learn_days", "pump_learn_hours",
    "pump_learn_bands", "pump_learn_mae", "pump_preview_status",
    "pump_preview_learned", "pump_preview_legacy", "pump_preview_delta",
    "calibration_status", "calibration_load_mae", "calibration_load_wape",
    "calibration_load_tested", "calibration_pv_discount",
    "calibration_ev_status", "calibration_ev_days", "calibration_ev_peak",
    "economic_ev_stress_import", "economic_ev_stress_soc",
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
        *[LabTestButton(coordinator, entry, test) for test in DIAGNOSTIC_TESTS],
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
    """Export one stable set of managed Lovelace files (never touch owner edits)."""
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
            "wymaga_jednorazowej_rejestracji_yaml": True,
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
        wanted.update({
            f"{self.entry.entry_id}_lab_{test}": f"lab_{test}"
            for test in DIAGNOSTIC_TESTS
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
            "source_battery": CONF_BATTERY_POWER,
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
        # Optional losses meter: use a real HA entity, not a guessed number.
        losses_candidates = []
        for item in self.coordinator.hass.states.async_all():
            entity_id = getattr(item, "entity_id", "")
            title = str((getattr(item, "attributes", {}) or {}).get("friendly_name", "")).lower()
            unit = (getattr(item, "attributes", {}) or {}).get("unit_of_measurement")
            if not entity_id.startswith("sensor.") or unit not in ("W", "kW"):
                continue
            if entity_id == "sensor.deye_power_losses" or (
                    "deye" in entity_id and "loss" in entity_id and "power" in entity_id
                    or "deye" in title and "power losses" in title):
                losses_candidates.append(entity_id)
        if len(set(losses_candidates)) == 1:
            sources["source_losses"] = losses_candidates[0]
        return ids, sources

    async def async_generate_managed_files(self):
        """Safe, idempotent export shared by user action and post-restart sync."""
        ids, sources = self._map_entities()
        forecast = await self.coordinator.hass.async_add_executor_job(
            Path(__file__).with_name("forecast_card.js").read_text, "utf-8",
        )
        overview = await self.coordinator.hass.async_add_executor_job(
            Path(__file__).with_name("overview_card.js").read_text, "utf-8",
        )
        cockpit = await self.coordinator.hass.async_add_executor_job(
            Path(__file__).with_name("control_card.js").read_text, "utf-8",
        )
        script = forecast + "\n" + overview + "\n" + cockpit
        full = render_dashboard(ids, sources)
        mini = render_mini_widget(ids, sources)
        paths = await self.coordinator.hass.async_add_executor_job(
            export_files, self.coordinator.hass.config.path(), full, mini, script,
        )
        return ids, sources, paths

    async def async_press(self) -> None:
        try:
            ids, sources, paths = await self.async_generate_managed_files()
        except (ValueError, OSError, RuntimeError) as exc:
            self._attr_extra_state_attributes = {
                "status": "Błąd eksportu",
                "przyczyna": str(exc)[:240],
                "wymaga_jednorazowej_rejestracji_yaml": True,
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
            "brakujace_opcjonalne_encje": [
                key for key in SENSOR_KEYS if key not in ids
            ],
            "liczba_zewnetrznych_czujnikow": len(sources),
            "wygenerowano_o": datetime.now(timezone.utc).isoformat(),
            "wymaga_jednorazowej_rejestracji_yaml": True,
            "eksport_staly_bez_duplikatow": True,
            "uwaga": "Po jednorazowej rejestracji YAML pliki są odświeżane także po restarcie HA. Dane odświeżają się na żywo. Pulpit UI z ręcznie wklejonym YAML nie aktualizuje układu z pliku.",
            "nie_modyfikuje_istniejacych_dashboardow": True,
            "nie_zmieniono_deye": True,
        }
        _LOGGER.info("ESTADI Lovelace export saved: %s", paths)
        self.async_write_ha_state()



class LabTestButton(ButtonEntity):
    """Manual, live diagnostic button. Cannot send any command to Deye."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator, entry, test: str):
        self.coordinator = coordinator
        self.entry = entry
        self.test = test
        self._attr_name = DIAGNOSTIC_TESTS[test]
        self._attr_unique_id = f"{entry.entry_id}_lab_{test}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }
        self._attr_extra_state_attributes = {
            "status": "nie_uruchomiono",
            "bez_zapisu_do_deye": True,
        }

    async def async_press(self) -> None:
        from datetime import datetime, timezone
        data = self.coordinator.data or {}
        settings = self.coordinator._selected_settings or {
            **self.entry.data, **self.entry.options,
        }
        try:
            result = inspect_test(
                self.test,
                states=self.coordinator.hass.states,
                selected=settings,
                coordinator_data=data,
                now=datetime.now(timezone.utc),
            )
        except Exception as exc:
            _LOGGER.exception("Błąd diagnostyki %s", self.test)
            result = {
                "test": self.test, "status": "blad",
                "reason": f"Test przerwany: {type(exc).__name__}",
                "command_sent": False,
            }
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        self.coordinator.lab_last_result = result
        self._attr_extra_state_attributes = result
        self.async_write_ha_state()
        self.coordinator.async_update_listeners()
