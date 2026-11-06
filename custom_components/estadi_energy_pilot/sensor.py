"""Calculated read-only advisory sensors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import UnitOfEnergy, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


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
                               "Brak prognozy na noc" if not d["night"].can_calculate else
                               "Brak prognozy na popołudnie" if not d["afternoon"].can_calculate else
                               "Plan gotowy")),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PilotSensor(coordinator, entry, description) for description in SENSORS])


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
        }
