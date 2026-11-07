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
    ("history_status", "Prognoza kontra pomiar PV — wczoraj", None),
    ("lab_status", "Laboratorium — wynik testu", None),
    ("grid_import", "Pobór z przyłącza", "kW"),
    ("grid_raw_power", "Deye — moc sieci surowa, ze znakiem", "kW"),
    ("grid_raw_status", "Deye — jakość pomiaru mocy sieci", None),
    ("grid_limit", "Limit przyłącza — ustawiony", "kW"),
    ("grid_headroom", "Dostępny zapas mocy przyłącza", "kW"),
    ("grid_charge_cap", "Orientacyjny limit ładowania (bez sterowania)", "kW"),
    ("grid_status", "Grid Guard — status", None),
    ("grid_reason", "Grid Guard — przyczyna", None),
    ("grid_phase_status", "Grid Guard — kontrola faz", None),
    ("grid_last_check", "Grid Guard — ostatni odczyt", None),
    ("grid_current_charge", "Grid Guard — moc ładowania magazynu", "kW"),
    ("deye_tou_status", "Deye TOU — stan rozpoznania", None),
    ("deye_tou_fields", "Deye TOU — poprawnie odczytane pola", None),
    ("deye_tou_snapshot", "Deye TOU — data migawki ustawień", None),
    ("deye_tou_changes", "Deye TOU — zmiany od migawki", None),
    ("deye_tou_ready", "Deye TOU — gotowość do automatyzacji", None),
    ("dry_run_status", "Dry-run — stan testu", None),
    ("dry_run_action", "Dry-run — hipotetyczna decyzja", None),
    ("dry_run_power", "Dry-run — hipotetyczna moc magazynu", "kW"),
    ("dry_run_samples", "Dry-run — zapisane decyzje", None),
    ("dry_run_days", "Dry-run — kompletne dni testów", None),
    ("dry_run_last", "Dry-run — ostatnia decyzja o", None),
    ("accuracy_status", "Weryfikacja prognoz — stan", None),
    ("accuracy_soc_3h", "Weryfikacja — odchylenie SOC 3h", "pp"),
    ("accuracy_soc_6h", "Weryfikacja — odchylenie SOC 6h", "pp"),
    ("accuracy_soc_12h", "Weryfikacja — odchylenie SOC 12h", "pp"),
    ("accuracy_soc_24h", "Weryfikacja — odchylenie SOC 24h", "pp"),
    ("accuracy_pv_wape", "Weryfikacja — błąd PV WAPE", "%"),
    ("accuracy_pv_days", "Weryfikacja — porównane dni PV", None),
    ("accuracy_plan_met", "Weryfikacja — cele SOC osiągnięte", None),
    ("accuracy_plan_missed", "Weryfikacja — cele SOC nieosiągnięte", None),

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
    ("sim_status", "Symulacja 48h — stan", None),
    ("sim_quality", "Symulacja 48h — wiarygodność", None),
    ("sim_hours", "Symulacja 48h — dostępne godziny", "h"),
    ("pv_coverage", "Prognoza PV — pokrycie słonecznych godzin 48h", "%"),
    ("sim_soc_end", "Symulacja 48h — SOC końcowy", "%"),
    ("sim_soc_min", "Symulacja 48h — minimalny SOC", "%"),
    ("sim_soc_min_cautious", "Symulacja 48h — minimalny SOC ostrożny", "%"),
    ("sim_grid_kwh", "Symulacja 48h — import z sieci", "kWh"),
    ("sim_pv_kwh", "Symulacja 48h — produkcja PV", "kWh"),
    ("sim_home_kwh", "Symulacja 48h — zużycie domu", "kWh"),
    ("sim_grid_peak", "Symulacja 48h — szczyt importu", "kW"),
    ("sim_cost", "Symulacja 48h — koszt importu", "PLN"),
    ("economic_status", "Opłacalność 48h — status", None),
    ("economic_base_cost", "Opłacalność — import bez dodatkowego ładowania", "PLN"),
    ("economic_plan_cost", "Opłacalność — import z planowanym ładowaniem", "PLN"),
    ("economic_import_delta", "Opłacalność — różnica kosztu importu", "PLN"),
    ("economic_base_export", "Opłacalność — eksport bez ładowania", "kWh"),
    ("economic_plan_export", "Opłacalność — eksport z ładowaniem", "kWh"),
    ("economic_base_soc", "Opłacalność — końcowy SOC bez ładowania", "%"),
    ("economic_plan_soc", "Opłacalność — końcowy SOC z ładowaniem", "%"),
    ("economic_terminal_delta", "Opłacalność — różnica końcowego SOC", "pp"),
    ("economic_estimate", "Opłacalność — porównywalna różnica salda", "PLN"),
    ("calibration_status", "Kalibracja — stan oceny modelu domu", None),
    ("pump_learn_status", "Pompa — stan uczenia temperatury", None),
    ("pump_excess_status", "Pompa — stan oceny nietypowego poboru", None),
    ("pump_excess_hours", "Pompa — porównane godziny", "h"),
    ("pump_excess_events", "Pompa — okresy podwyższonego poboru", None),
    ("pump_excess_kwh", "Pompa — szacowana nadwyżka poboru", "kWh"),
    ("pump_excess_last", "Pompa — ostatni nietypowy pobór", None),
    ("pump_learn_days", "Pompa — kompletne dni pomiarów temperatury", None),
    ("pump_learn_hours", "Pompa — godziny sparowane z temperaturą", "h"),
    ("pump_learn_bands", "Pompa — wyuczone zakresy temperatury", None),
    ("pump_learn_mae", "Pompa — błąd prognozy poboru", "kWh"),
    ("pump_preview_status", "Pompa — stan porównania 48h", None),
    ("pump_preview_learned", "Pompa — model wyuczony 48h", "kWh"),
    ("pump_preview_legacy", "Pompa — dotychczasowy model 48h", "kWh"),
    ("pump_preview_delta", "Pompa — różnica prognozy 48h", "kWh"),
    ("calibration_load_mae", "Kalibracja — błąd profilu domu", "kWh"),
    ("calibration_load_wape", "Kalibracja — WAPE profilu domu", "%"),
    ("calibration_load_tested", "Kalibracja — przetestowane godziny", None),
    ("calibration_pv_discount", "Kalibracja — sugerowana całkowita korekta PV", "%"),
    ("calibration_ev_status", "EV — stan historycznego scenariusza ryzyka", None),
    ("calibration_ev_days", "EV — liczba dni pełnych pomiarów", None),
    ("calibration_ev_peak", "EV — szczyt stresowy z historii", "kW"),
    ("economic_ev_stress_import", "Opłacalność — import z planem i ryzykiem EV", "kWh"),
    ("economic_ev_stress_soc", "Opłacalność — SOC z planem i ryzykiem EV", "%"),
    ("smart_charge_status", "Inteligentne ładowanie — stan", None),
    ("smart_charge_power", "Inteligentne ładowanie — proponowana moc", "kW"),
    ("smart_charge_start", "Inteligentne ładowanie — godzina startu", None),
    ("smart_charge_finish", "Inteligentne ładowanie — przewidywany koniec", None),
    ("smart_charge_target", "Inteligentne ładowanie — cel SOC", "%"),
    ("smart_charge_energy", "Inteligentne ładowanie — energia z sieci", "kWh"),
    ("smart_charge_peak", "Inteligentne ładowanie — szczyt poboru", "kW"),
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
        sim = d.get("simulation_48h") or {}
        pv_coverage = d.get("pv_coverage") or {}
        economy = d.get("scenario_economics") or {}
        economic_base = economy.get("baseline") or {}
        economic_plan = economy.get("plan") or {}
        stress = economy.get("ev_stress") or {}
        stress_plan = stress.get("plan") or {}
        pump_excess = d.get("pump_excess") or {}
        pump_model = d.get("heat_pump_learning") or {}
        pump_preview = pump_model.get("preview_48h") or {}
        calibration = d.get("calibration") or {}
        house_calibration = calibration.get("load") or {}
        pv_calibration = calibration.get("pv") or {}
        ev_calibration = calibration.get("ev") or {}
        ev_profiles = ev_calibration.get("profiles") or {}
        ev_peaks = [item.get("peak_hour_kwh") for item in ev_profiles.values()
                    if isinstance(item, dict) and item.get("peak_hour_kwh") is not None]
        cautious = sim.get("cautious") or {}
        smart = d.get("optimized_schedule") or {}
        tou = d.get("deye_tou") or {}
        dry = d.get("dry_run") or {}
        latest = dry.get("ostatnia_decyzja") or {}
        accuracy = d.get("accuracy") or {}
        horizons = accuracy.get("horyzonty_soc") or {}
        pv_accuracy = accuracy.get("pv") or {}
        outcomes = accuracy.get("obserwacje_celu") or {}
        values = {
            "pump_excess_status": pump_excess.get("status", "brak_danych"),
            "pump_excess_hours": pump_excess.get("hours_compared_with_older_days"),
            "pump_excess_events": pump_excess.get("event_count"),
            "pump_excess_kwh": pump_excess.get("estimated_excess_energy_kwh"),
            "pump_excess_last": pump_excess.get("last_event_start"),
            "pump_learn_status": pump_model.get("status", "brak_danych"),
            "pump_learn_days": pump_model.get("days_complete"),
            "pump_learn_hours": pump_model.get("valid_hours"),
            "pump_learn_bands": pump_model.get("learned_bands"),
            "pump_learn_mae": pump_model.get("mae_kwh_h"),
            "pump_preview_status": pump_preview.get("status", "brak_danych"),
            "pump_preview_learned": pump_preview.get("prognoza_nauczona_kwh"),
            "pump_preview_legacy": pump_preview.get("prognoza_dotychczasowa_kwh"),
            "pump_preview_delta": pump_preview.get("roznica_kwh"),
            "calibration_status": house_calibration.get("status", "brak_danych"),
            "calibration_load_mae": house_calibration.get("mae_kwh_hour"),
            "calibration_load_wape": house_calibration.get("wape_pct"),
            "calibration_load_tested": house_calibration.get("tested_hours"),
            "calibration_pv_discount": pv_calibration.get("suggested_total_pv_discount_pct"),
            "calibration_ev_status": ev_calibration.get("status", "brak_danych"),
            "calibration_ev_days": ev_calibration.get("complete_days"),
            "calibration_ev_peak": round(max(ev_peaks), 2) if ev_peaks else None,
            "economic_ev_stress_import": stress_plan.get("import_kwh"),
            "economic_ev_stress_soc": stress_plan.get("soc_end_pct"),
            "economic_status": economy.get("status", "brak_danych"),
            "economic_base_cost": economic_base.get("import_cost_pln"),
            "economic_plan_cost": economic_plan.get("import_cost_pln"),
            "economic_import_delta": economy.get("import_cost_delta_pln"),
            "economic_base_export": economic_base.get("export_kwh"),
            "economic_plan_export": economic_plan.get("export_kwh"),
            "economic_base_soc": economic_base.get("soc_end_pct"),
            "economic_plan_soc": economic_plan.get("soc_end_pct"),
            "economic_terminal_delta": economy.get("terminal_soc_difference_pp"),
            "economic_estimate": economy.get("estimated_balance_advantage_pln"),
            "accuracy_status": accuracy.get("stan", "brak_danych"),
            "accuracy_soc_3h": (horizons.get("3") or {}).get("mae_soc_pp"),
            "accuracy_soc_6h": (horizons.get("6") or {}).get("mae_soc_pp"),
            "accuracy_soc_12h": (horizons.get("12") or {}).get("mae_soc_pp"),
            "accuracy_soc_24h": (horizons.get("24") or {}).get("mae_soc_pp"),
            "accuracy_pv_wape": pv_accuracy.get("wape_pct"),
            "accuracy_pv_days": pv_accuracy.get("dni"),
            "accuracy_plan_met": outcomes.get("cel_osiagniety"),
            "accuracy_plan_missed": outcomes.get("cel_nieosiagniety"),

            "dry_run_status": dry.get("status", "brak_pomiarow"),
            "dry_run_action": latest.get("hipotetyczna_akcja"),
            "dry_run_power": latest.get("suggested_kw"),
            "dry_run_samples": dry.get("zapisanych_decyzji"),
            "dry_run_days": dry.get("pelnych_dni_testu"),
            "dry_run_last": dry.get("ostatnia_proba"),
            "deye_tou_status": tou.get("status", "brak_danych"),
            "deye_tou_fields": tou.get("odczytane_pola"),
            "deye_tou_snapshot": tou.get("migawka_o"),
            "deye_tou_changes": tou.get("liczba_zmian"),
            "deye_tou_ready": "NIE — tylko odczyt",
            "smart_charge_status": smart.get("status", "brak_danych"),
            "smart_charge_power": smart.get("power_kw"),
            "smart_charge_start": smart.get("start"),
            "smart_charge_finish": smart.get("finish_estimated"),
            "smart_charge_target": smart.get("target_soc"),
            "smart_charge_energy": smart.get("grid_charge_kwh"),
            "smart_charge_peak": smart.get("grid_peak_kw"),
            "sim_status": sim.get("status", "brak_danych"),
            "sim_quality": sim.get("quality"),
            "sim_hours": sim.get("forecast_hours"),
            "pv_coverage": pv_coverage.get("covered_daylight_pct"),
            "sim_soc_end": sim.get("soc_end_pct"),
            "sim_soc_min": sim.get("soc_min_pct"),
            "sim_soc_min_cautious": cautious.get("soc_min_pct"),
            "sim_grid_kwh": sim.get("grid_import_kwh"),
            "sim_pv_kwh": sim.get("pv_kwh"),
            "sim_home_kwh": sim.get("house_kwh"),
            "sim_grid_peak": sim.get("grid_peak_kw"),
            "sim_cost": sim.get("cost_import_pln"),
            "mini_status": mini,
            "history_status": ("Zapisano " + str(sum(1 for row in ((self.coordinator.data or {}).get("history_hours") or []) if row.get("forecast_kwh") is not None or row.get("actual_kwh") is not None)) + " godzin"),
            "lab_status": (getattr(self.coordinator, "lab_last_result", {}) or {}).get("status", "nie_uruchomiono"),
            "grid_import": g.get("import_kw"),
            "grid_raw_power": g.get("raw_grid_kw"),
            "grid_raw_status": g.get("raw_grid_status"),
            "grid_limit": g.get("connection_limit_kw"),
            "grid_headroom": g.get("headroom_kw"),
            "grid_charge_cap": g.get("allowed_charge_kw"),
            "grid_status": g.get("state"),
            "grid_reason": g.get("reason"),
            "grid_phase_status": g.get("phase_status"),
            "grid_last_check": g.get("guard_last_checked"),
            "grid_current_charge": g.get("current_charge_kw"),
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
        if self._key == "lab_status":
            recent = getattr(self.coordinator, "lab_last_result", {}) or {}
            return {
                "test": recent.get("test"),
                "przyczyna": recent.get("reason"),
                "szczegoly": recent,
                "ostatni_test": recent.get("checked_at"),
                "bez_zapisu_deye": True,
            }
        if self._key == "history_status":
            snapshot = self.coordinator.data or {}
            return {
                "godziny": (snapshot.get("history_hours") or [])[:24],
                "dzien": (snapshot.get("history_yesterday") or {}).get("date"),
                "kompletnosc_pv_pct": (snapshot.get("history_yesterday") or {}).get("pv_coverage_pct"),
                "pomiar_rzeczywisty_to_nie_symulacja": True,
            }
        d = (self.coordinator.data or {}).get("energy_2_0", {})
        if self._key == "pump_excess_status":
            review = d.get("pump_excess") or {}
            return {
                "godziny_poprawnych_pomiarow": review.get("hours_with_temperature_and_energy"),
                "godziny_porownywalne": review.get("hours_compared_with_older_days"),
                "dni_porownywalne": review.get("days_evaluated"),
                "godziny_z_podwyzszonym_poborem": review.get("suspected_high_load_hours"),
                "ostatnie_okresy": review.get("latest_events", []),
                "prog_minimalnej_nadwyzki_kwh_na_godzine": review.get("min_excess_kwh_per_hour"),
                "mnoznik_historycznego_p90": review.get("p90_multiplier"),
                "potwierdzone_cykle_CWU": None,
                "potwierdzone_odszraniania": None,
                "automatyczne_sterowanie": False,
                "interpretacja": review.get("interpretation"),
            }
        if self._key == "pump_learn_status":
            pump = d.get("heat_pump_learning") or {}
            return {
                "model_wyuczony_w_zakresach": pump.get("bands", {}),
                "wymagania": pump.get("requirements", {}),
                "jakosc": pump.get("quality"),
                "godziny_testowane": pump.get("holdout_hours"),
                "dni_testowane": pump.get("holdout_days"),
                "odchylenie_modelu_kwh_h": pump.get("bias_actual_minus_model_kwh_h"),
                "zrodlo_temperatury": pump.get("temperature_sensor"),
                "pomiar_temperatury_c": pump.get("measured_temperature_c"),
                "status_czujnika": pump.get("sensor_status"),
                "porownanie_48h": pump.get("preview_48h"),
                "automatyczne_ustawianie_pompy": False,
                "automatyczna_zmiana_planu_magazynu": False,
                "uwagi": pump.get("note"),
            }
        if self._key == "calibration_status":
            calibration = d.get("calibration") or {}
            return {
                "profil_domu_analiza_wsteczna": calibration.get("load"),
                "ev_historyczny_scenariusz_stresowy": calibration.get("ev"),
                "korekta_pv_rekomendacja": calibration.get("pv"),
                "automatyczne_zmiany_wylaczone": True,
                "dodatkowe_ladowanie_EV_niepotwierdzone": True,
                "uwaga": "Deye Load zawiera EV i pompę; model wyłącza je z profilu bazowego.",
            }
        if self._key == "economic_status":
            ec = d.get("scenario_economics") or {}
            base = ec.get("baseline") or {}
            planned = ec.get("plan") or {}
            return {
                "przyczyna": ec.get("reason"),
                "taryfa": ec.get("tariff"),
                "ceny_zakupu_potwierdzone": ec.get("import_prices_confirmed"),
                "wartosc_eksportu_potwierdzona": ec.get("export_price_confirmed"),
                "szacunkowa_wartosc_eksportu_pln_kwh": ec.get("export_value_pln_kwh"),
                "scenariusz_bez_ladowania": base,
                "scenariusz_z_planem": planned,
                "historyczny_wariant_ryzyka_EV": ec.get("ev_stress"),
                "roznica_kosztu_importu_pln": ec.get("import_cost_delta_pln"),
                "roznica_saldu_przed_korekta_soc_pln": ec.get("unadjusted_balance_difference_pln"),
                "roznica_soc_koncowego_pp": ec.get("terminal_soc_difference_pp"),
                "przyblizona_roznica_saldu_przy_podobnym_soc_pln": ec.get("estimated_balance_advantage_pln"),
                "rzeczywiste_oszczednosci_pln": None,
                "sterowanie_deye_wykonane": False,
                "uwagi": ec.get("note"),
            }
        if self._key == "accuracy_status":
            accuracy = d.get("accuracy") or {}
            return {
                "porownania_soc": accuracy.get("horyzonty_soc", {}),
                "kontrola_celow_soc": accuracy.get("obserwacje_celu", {}),
                "skutecznosc_pv": accuracy.get("pv", {}),
                "ostatnie_porownania": accuracy.get("ostatnie_12", []),
                "pomiar_soc": accuracy.get("soc_pomiar_status"),
                "zmierzony_soc": accuracy.get("ostatni_zmierzony_soc"),
                "brak_odczytow_w_terminie": accuracy.get("brak_odczytu_w_terminie", 0),
                "liczba_migawek": accuracy.get("liczba_migawek", 0),
                "interpretacja": accuracy.get("uwaga"),
                "oszczednosci_rzeczywiste_pln": None,
                "sterowanie_deye_wylaczone": True,
            }
        if self._key in ("dry_run_status", "dry_run_action", "dry_run_power"):
            dry = d.get("dry_run") or {}
            latest = dry.get("ostatnia_decyzja") or {}
            return {
                "hipotetyczna_decyzja": latest,
                "wymagane_dni": dry.get("wymagane_dni_testu", 7),
                "pelne_dni": dry.get("pelnych_dni_testu", 0),
                "dni_pozostale": dry.get("dni_do_testu", 7),
                "ostatnie_20_decyzji": dry.get("ostatnie_zdarzenia", []),
                "autostart_automatyzacji": False,
                "faktycznie_wyslane_polecenia": 0,
                "bez_zapisu_do_deye": True,
            }
        if self._key in ("deye_tou_status", "deye_tou_ready", "deye_tou_changes"):
            tou = d.get("deye_tou") or {}
            return {
                "przyczyna": tou.get("przyczyna"),
                "programy_1_do_6": tou.get("programy", []),
                "stan_globalny": tou.get("stan_globalny", {}),
                "inne_mozliwe_encje": tou.get("inne_mozliwe_encje", []),
                "blokady_uruchomienia": tou.get("blokady", []),
                "odczytane_pola": tou.get("odczytane_pola"),
                "brakujace_pola": tou.get("brakujace_pola"),
                "migawka_o": tou.get("migawka_o"),
                "zmiany_w_ustawieniach": tou.get("zmiany_od_migawki", []),
                "odczyt_o": tou.get("odczyt_o"),
                "nie_wykonano_zadnych_polecen": True,
            }
        if self._key == "smart_charge_status":
            smart = d.get("optimized_schedule") or {}
            return {
                "przyczyna": smart.get("reason"),
                "prognozowany_soc_na_koniec": smart.get("end_soc"),
                "przydzielona_moc_kw": smart.get("power_kw"),
                "pobor_szacowany_kw": smart.get("grid_peak_kw"),
                "limit_roboczy_kw": smart.get("soft_limit_kw"),
                "energia_z_sieci_kwh": smart.get("grid_charge_kwh"),
                "warianty_ladowania": smart.get("alternatives", []),
                "ograniczenia": smart.get("limitations", []),
                "auto_wyłączone": True,
                "czy_wykonano_sterowanie": False,
                "wykres_48h": "Symulacja 48h — stan",
            }
        if self._key == "pv_coverage":
            report = d.get("pv_coverage") or {}
            return {
                "zrodlo": report.get("source"),
                "pierwsza_luka_sloneczna": report.get("first_missing_daylight_at"),
                "liczba_slonecznych_przedzialow": report.get("required_daylight_steps"),
                "otrzymane_sloneczne_przedzialy": report.get("available_daylight_steps"),
                "ciagle_pokryte_sloneczne_przedzialy": report.get("continuous_daylight_steps"),
                "brakujace_sloneczne_przedzialy": report.get("missing_daylight_steps"),
                "brak_punktow_przy_niskim_sloncu": report.get("lowlight_assumed_zero_steps"),
                "ostatni_koniec_prognozy": report.get("last_forecast_end_at"),
                "liczba_punktow": report.get("time_steps"),
                "warianty_zrodel": report.get("candidate_sources"),
                "konieczne_polozenie_instalacji": True,
                "wspolrzedne_z_Home_Assistant": report.get("location_confirmed"),
                "nie_dopisano_prognozy_na_dzien": True,
            }
        if self._key == "sim_status":
            sim = d.get("simulation_48h") or {}
            return {
                "przyczyna": sim.get("reason"),
                "harmonogram_48h": sim.get("timeline_hours", []),
                "wariant_ostrozny": sim.get("cautious"),
                "jakosc": sim.get("quality"),
                "przedzial_minut": 15,
                "nocne_przedzialy_uznane_za_zero": sim.get("lowlight_assumed_zero_steps"),
                "wariant": sim.get("scenario"),
                "przyszle_ladowanie_EV_nieznane": sim.get("future_ev_sessions_unknown"),
                "prognoza_nie_jest_pomiarem": True,
                "nie_steruje_magazynem": True,
            }
        if self._key == "mini_status":
            return {
                "moc_biezaca": d.get("live"),
                "grid_guard": d.get("grid"),
                "cel_i_start": d.get("charging_schedule"),
                "plan_15min": d.get("optimized_schedule"),
                "taryfa": d.get("tariff"),
                "automatyzacja_wlaczona": False,
            }
        if self._key in ("grid_status", "grid_phase_status", "grid_raw_power", "grid_raw_status"):
            g = d.get("grid", {})
            return {
                "szczegoly": g,
                "surowy_pomiar_to_nie_import": True,
                "kierunek_importu_potwierdzony": g.get("import_sign_confirmed"),
                "zrodlo_deye": g.get("raw_grid_entity_id"),
                "stan_zrodel": g.get("source_status", {}),
                "kontrola_faz": g.get("phase_status"),
                "limity_pradu_faz_a": g.get("nominal_phase_limits_a"),
                "czy_mozna_sterowac": False,
                "automatyzacja_wlaczona": False,
            }
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
            "pompa_wliczona_w_dom": learning.get("heat_pump_in_home_load"),
            "dni_kompletne_dla_profilu_bazowego": learning.get("baseline_complete_days", 0),
            "profil_bazowy_gotowy": learning.get("baseline_ready", False),
            "odczyty_niespojne": learning.get("inconsistent_hours", 0),
            "profil_godzinowy_bez_ev": learning.get("profiles", {}),
            "profil_godzinowy_bez_ev_i_pompy": learning.get("base_profiles", {}),
            "uwagi": learning.get("note", "Brak historii"),
        }
