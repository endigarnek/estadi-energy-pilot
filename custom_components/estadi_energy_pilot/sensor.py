"""Calculated read-only advisory sensors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import UnitOfEnergy, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_VERSION


@dataclass(frozen=True, kw_only=True)
class PilotSensorDescription(SensorEntityDescription):
    accessor: Callable = lambda data: None


SENSORS = (
    PilotSensorDescription(key="night_target_soc", name="Noc: docelowy SOC", native_unit_of_measurement=PERCENTAGE,
                           accessor=lambda d: d["night"].target_soc if d["night"].can_calculate else None),
    PilotSensorDescription(key="afternoon_target_soc", name="Popołudnie: docelowy SOC", native_unit_of_measurement=PERCENTAGE,
                           accessor=lambda d: d["afternoon"].target_soc if d["afternoon"].can_calculate else None),
    PilotSensorDescription(key="night_pv_kwh", name="Prognoza PV: 07–13", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                           accessor=lambda d: d["night"].pv_kwh if d["night"].can_calculate else None),
    PilotSensorDescription(key="afternoon_pv_kwh", name="Prognoza PV: 16–21", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                           accessor=lambda d: d["afternoon"].pv_kwh if d["afternoon"].can_calculate else None),
    PilotSensorDescription(key="night_load_kwh", name="Zużycie: 07–13", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                           accessor=lambda d: d["night"].load_kwh),
    PilotSensorDescription(key="afternoon_load_kwh", name="Zużycie: 16–21", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                           accessor=lambda d: d["afternoon"].load_kwh),
    PilotSensorDescription(key="charge_needed_kwh", name="Dodatkowe ładowanie teraz", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                           accessor=lambda d: d["charge_needed_kwh"]),
    PilotSensorDescription(key="charge_window", name="Aktualne okno taryfowe",
                           accessor=lambda d: {"night": "Noc", "afternoon": "Popołudnie", None: "Droga energia"}[d["charge_window"]]),
    PilotSensorDescription(key="status", name="Stan obliczeń",
                           accessor=lambda d: (
                               d.get("forecast_error") if
                               d.get("forecast_error") and not d["night"].can_calculate else
                               "Brak prognozy na noc" if not d["night"].can_calculate else
                               "Brak prognozy na popołudnie" if not d["afternoon"].can_calculate else
                               "Plan gotowy")),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VersionSensor(entry)] +
                       [PilotSensor(coordinator, entry, description) for description in SENSORS] +
                       [HistorySensor(coordinator, entry, key, title, unit, field) for key, title, unit, field in HISTORY_SENSORS])


class PilotSensor(CoordinatorEntity, SensorEntity):
    entity_description: PilotSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "ESTADI Energy Pilot",
                                  "manufacturer": "ESTADI", "model": "Energy Pilot — doradczy"}

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data or not data.get("available"):
            return data.get("reason", "Brak danych") if self.entity_description.key == "status" and data else None
        return self.entity_description.accessor(data)

    @property
    def extra_state_attributes(self):
        if self.entity_description.key != "status":
            return None
        data = self.coordinator.data
        if not data or not data.get("available"):
            return None
        return {
            "noc_okres": f'{data["night"].start.isoformat()} → {data["night"].end.isoformat()}',
            "popoludnie_okres": f'{data["afternoon"].start.isoformat()} → {data["afternoon"].end.isoformat()}',
            "noc_uzasadnienie": data["night"].reason,
            "popoludnie_uzasadnienie": data["afternoon"].reason,
            "prognoza_temperatury": data["temperature_source"],
            "odczytane_przedzialy_pv": data["forecast_intervals"],
            "zrodlo_prognozy": data.get("forecast_source"),
            "blad_prognozy": data.get("forecast_error"),
        }


HISTORY_SENSORS = (
    ("pv_forecast_yesterday", "Wczorajsza prognoza PV (z 21:00)", "kWh", "forecast_pv_kwh"),
    ("pv_actual_yesterday", "Wczorajsza produkcja PV — pomiar", "kWh", "pv_kwh"),
    ("pv_error_yesterday", "Błąd wczorajszej prognozy PV", "kWh", "pv_error_kwh"),
    ("pv_coverage_yesterday", "Kompletność pomiaru PV wczoraj", "%", "pv_coverage_pct"),
    ("ev_yesterday", "Energia ładowarki EV wczoraj (szacowana)", "kWh", "ev_kwh"),
    ("ev_today", "Energia ładowarki EV dzisiaj (szacowana)", "kWh", "ev_kwh"),
    ("heat_pump_yesterday", "Energia pompy ciepła wczoraj (szacowana)", "kWh", "heat_pump_kwh"),
    ("pv_today", "Produkcja PV dzisiaj (szacowana)", "kWh", "pv_kwh"),
    ("pv_last_hour_forecast", "PV: prognoza poprzedniej godziny", "kWh", "forecast_kwh"),
    ("pv_last_hour_actual", "PV: rzeczywista poprzednia godzina", "kWh", "actual_kwh"),
)


class HistorySensor(CoordinatorEntity, SensorEntity):
    """History remains visible even if battery state is currently unavailable."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, title, unit, field):
        super().__init__(coordinator)
        self._key = key
        self._field = field
        self._attr_name = title
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)},
                                  "name": "ESTADI Energy Pilot"}

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self._key in ("pv_last_hour_forecast", "pv_last_hour_actual"):
            sample = data.get("history_last_hour") or {}
            if self._key == "pv_last_hour_actual" and sample.get("coverage_pct", 0) < 90:
                return None
            return sample.get(self._field)
        day = data.get("history_today" if self._key in ("ev_today", "pv_today") else "history_yesterday", {})
        if self._key == "pv_actual_yesterday" and day.get("pv_coverage_pct", 0) < 90:
            return None
        if self._key == "pv_error_yesterday" and not day.get("comparable"):
            return None
        return day.get(self._field)

    @property
    def extra_state_attributes(self):
        if self._key in ("pv_last_hour_forecast", "pv_last_hour_actual"):
            data = self.coordinator.data or {}
            return {"okres_od": data.get("history_last_hour_at"),
                    "pokrycie_pomiaru": (data.get("history_last_hour") or {}).get("coverage_pct")}
        if self._key != "pv_error_yesterday":
            return None
        data = self.coordinator.data or {}
        return {"ostatnie_dni": data.get("history_recent", []),
                "godziny_wczoraj": data.get("history_hours", []),
                "dane_niepelne_nie_sa_oceniane": True}


class VersionSensor(SensorEntity):
    """Diagnostic version that remains available when PV forecast is missing."""
    _attr_has_entity_name = True
    _attr_name = "Wersja integracji"
    _attr_icon = "mdi:information-outline"

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_integration_version"
        self._attr_native_value = INTEGRATION_VERSION
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }
