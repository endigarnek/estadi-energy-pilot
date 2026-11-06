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
                       [HealthSensor(coordinator, entry, kind) for kind in ("status", "last_refresh", "last_success", "refresh_count", "error_count", "last_duration_ms")] +
                       [PilotSensor(coordinator, entry, description) for description in SENSORS] +
                       [HistorySensor(coordinator, entry, key, title, unit, field) for key, title, unit, field in HISTORY_SENSORS] +
                       [EnergyV2Sensor(coordinator, entry, key, name, unit) for key, name, unit in ENERGY_V2_SENSORS] +
                       [HouseLearningSensor(coordinator, entry)])


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
        if not data:
            return None
        if not data.get("available"):
            return {"diagnostyka": data.get("diagnostics", {}),
                    "przyczyna": data.get("reason")}
        return {
            "diagnostyka": data.get("diagnostics", {}),
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


class HealthSensor(CoordinatorEntity, SensorEntity):
    """A health probe independent of whether the PV plan is available."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:heart-pulse"
    _NAMES = {
        "status": "Stan systemu",
        "last_refresh": "Ostatnie odświeżenie",
        "last_success": "Ostatni poprawny plan",
        "refresh_count": "Liczba odświeżeń",
        "error_count": "Liczba błędów",
        "last_duration_ms": "Czas ostatniego odświeżenia",
    }

    def __init__(self, coordinator, entry, kind):
        super().__init__(coordinator)
        self._kind = kind
        self._attr_name = self._NAMES[kind]
        self._attr_unique_id = f"{entry.entry_id}_health_{kind}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }
        if kind == "last_duration_ms":
            self._attr_native_unit_of_measurement = "ms"

    @property
    def native_value(self):
        health = self.coordinator.diagnostics()
        kind = self._kind
        if kind == "status":
            return {
                "ok": "Działa",
                "warning": "Ograniczony",
                "error": "Błąd",
                "brak_odswiezania": "Brak odświeżania",
                "start": "Uruchamianie",
            }.get(health["status"], "Nieznany")
        fields = {
            "last_refresh": "last_completed",
            "last_success": "last_success",
            "refresh_count": "refresh_count",
            "error_count": "error_count",
            "last_duration_ms": "duration_ms",
        }
        return health.get(fields[kind])

    @property
    def extra_state_attributes(self):
        if self._kind != "status":
            return None
        info = self.coordinator.diagnostics()
        return {
            "przyczyna": info["reason"],
            "ostatnia_proba": info["last_attempt"],
            "ostatnie_odswiezenie": info["last_completed"],
            "ostatni_poprawny_plan": info["last_success"],
            "wiek_odswiezenia_s": info["age_seconds"],
            "liczba_odswiezen": info["refresh_count"],
            "liczba_bledow": info["error_count"],
            "czas_odswiezenia_ms": info["duration_ms"],
            "dziennik_ostatnich_zdarzen": info["events"],
        }


ENERGY_V2_SENSORS = (
    ("mini_status", "Szybki status energii", None),
    ("grid_import", "Pobór z przyłącza", "kW"),
    ("grid_headroom", "Dostępny zapas mocy przyłącza", "kW"),
    ("grid_charge_cap", "Orientacyjny limit ładowania (bez sterowania)", "kW"),
    ("grid_status", "Grid Guard — status", None),
    ("grid_reason", "Grid Guard — przyczyna", None),
    ("tariff", "Taryfa", None),
    ("tariff_zone", "Aktualna strefa taryfowa", None),
    ("tariff_price", "Cena w aktualnej strefie", "PLN/kWh"),
    ("next_cheap", "Początek następnej taniej strefy", None),
    ("battery_nominal", "Pojemność nominalna magazynu", "kWh"),
    ("battery_window", "Energia w zakresie SOC", "kWh"),
    ("plan_status", "Plan ładowania — status", None),
    ("plan_start", "Plan ładowania — start", None),
    ("plan_power", "Plan ładowania — moc zalecana", "kW"),
    ("plan_target", "Plan ładowania — docelowy SOC", "%"),
)


class EnergyV2Sensor(CoordinatorEntity, SensorEntity):
    """Interpret advisory outputs without confusing them with executed writes."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, title, unit):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = title
        self._attr_unique_id = f"{entry.entry_id}_ep20_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }

    @property
    def native_value(self):
        d = (self.coordinator.data or {}).get("energy_2_0", {})
        g, model = d.get("grid", {}), d.get("model", {})
        p = d.get("charging_schedule") or {}
        live = d.get("live", {})
        soc = d.get("current_soc_pct")
        imported = g.get("import_kw")
        ev = live.get("ev_kw")
        mini = " | ".join((
            f"SOC {soc}%" if soc is not None else "SOC: brak",
            f"Sieć {imported}/{g.get('connection_limit_kw')} kW" if imported is not None else "Sieć: brak kalibracji",
            f"Auto {ev} kW" if ev is not None else "Auto: brak danych",
        ))
        values = {
            "mini_status": mini,
            "grid_import": g.get("import_kw"),
            "grid_headroom": g.get("headroom_kw"),
            "grid_charge_cap": g.get("allowed_charge_kw"),
            "grid_status": g.get("state"),
            "grid_reason": g.get("reason"),
            "tariff": d.get("tariff"),
            "tariff_zone": d.get("tariff_zone"),
            "tariff_price": d.get("price_current_pln_kwh"),
            "next_cheap": d.get("next_cheap_start"),
            "battery_nominal": model.get("nominal_kwh"),
            "battery_window": model.get("soc_window_kwh"),
            "plan_status": p.get("state") or d.get("schedule_note", "Brak planu"),
            "plan_start": p.get("start"),
            "plan_power": p.get("power_kw"),
            "plan_target": p.get("target_soc"),
        }
        return values.get(self._key)

    @property
    def extra_state_attributes(self):
        d = (self.coordinator.data or {}).get("energy_2_0", {})
        if self._key == "mini_status":
            return {
                "moc_biezaca": d.get("live"),
                "grid_guard": d.get("grid"),
                "cel_i_start": d.get("charging_schedule"),
                "taryfa": d.get("tariff"),
                "automatyzacja_wlaczona": False,
            }
        if self._key == "grid_status":
            return {"szczegoly": d.get("grid"), "automatyzacja_wlaczona": False}
        if self._key == "plan_status":
            return {"harmonogram": d.get("charging_schedule"),
                    "strefa": d.get("tariff_zone"),
                    "bez_wykonania": True}
        return None


class HouseLearningSensor(CoordinatorEntity, SensorEntity):
    """Training progress and robust profiles, without assuming EV topology."""
    _attr_has_entity_name = True
    _attr_name = "Uczenie zużycia domu"
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_house_learning"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }

    @property
    def native_value(self):
        learning = (self.coordinator.data or {}).get("energy_2_0", {}).get("house_learning", {})
        return {"gotowy": "Gotowy", "ucze_sie": "Uczę się",
                "niepotwierdzona_topologia_ev": "Sprawdź czy EV jest w Deye Load"}.get(
                    learning.get("state"), "Brak danych")

    @property
    def extra_state_attributes(self):
        learning = (self.coordinator.data or {}).get("energy_2_0", {}).get("house_learning", {})
        return {
            "kompletne_dni": learning.get("complete_days", 0),
            "wymagane_dni": learning.get("required_days", 7),
            "dni_pominiete": learning.get("skipped_days", 0),
            "ev_wliczony_w_dom": learning.get("ev_in_home_load"),
            "profil_godzinowy": learning.get("profiles", {}),
            "uwagi": learning.get("note", "Brak historii"),
        }
