"""48-hour quarter-hour SOC simulation — read only, with explicit uncertainty.

Deye Load includes EV and heat pump. The *learned baseline* must exclude both
before adding forecast heat pump exactly once. Future EV sessions are UNKNOWN:
only the currently measured EV power is modeled for the first 15-minute slot.
No guessed future EV charging, no battery/grid control, no invented savings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt

from .battery_model import BatteryModel
from .engine import PvSlot, TempSlot, pump_power_w
from .tariffs import tariff_zone, is_day_off, WARSAW
from .solar_geometry import required_forecast

STEP_MINUTES = 15
STEPS_48H = 48 * 60 // STEP_MINUTES
MIN_BASE_SAMPLES = 3


def _is_finite_nonnegative(value) -> bool:
    return isinstance(value, (int, float)) and isfinite(value) and value >= 0


def _slot_energy(start: datetime, end: datetime, slots: list[PvSlot]) -> tuple[float, float]:
    """Return energy (kWh) and fraction of step covered by valid PV forecast."""
    produced = covered = 0.0
    for slot in slots:
        if not _is_finite_nonnegative(slot.power_kw) or slot.duration_minutes <= 0:
            continue
        slot_start = slot.start.astimezone(timezone.utc)
        slot_end = slot_start + timedelta(minutes=slot.duration_minutes)
        seconds = max(0.0, (min(end, slot_end) - max(start, slot_start)).total_seconds())
        if seconds <= 0:
            continue
        produced += slot.power_kw * seconds / 3600
        covered += seconds
    step_seconds = (end - start).total_seconds()
    return produced, min(1., covered / step_seconds)


def _temperature(at: datetime, forecast: list[TempSlot], fallback: float) -> tuple[float, bool]:
    candidates = [slot for slot in forecast if slot.start <= at and isfinite(slot.degrees_c)]
    if candidates:
        last = max(candidates, key=lambda row: row.start)
        if 0 <= (at - last.start).total_seconds() <= 3 * 3600:
            return last.degrees_c, True
    return fallback, False


def _base_kwh_per_hour(at: datetime, learning: dict, fallback_w: float, variant: str) -> tuple[float, bool]:
    """P50/P90 home without EV and without pump; never use untrained histories."""
    if learning.get("baseline_ready"):
        group = "weekend" if is_day_off(at.date()) else "weekday"
        rows = learning.get("base_profiles", {}).get(group, [])
        if len(rows) == 24:
            row = rows[at.hour]
            key = "p90_kwh" if variant == "ostrozny" else "p50_kwh"
            value = row.get(key)
            if _is_finite_nonnegative(value) and row.get("sample_count", 0) >= MIN_BASE_SAMPLES:
                return float(value), True
    return fallback_w / 1000, False


def _round_data(row: dict) -> dict:
    return {key: round(value, 3) if isinstance(value, float) else value
            for key, value in row.items()}


def _calculate(
    now: datetime, pv_slots: list[PvSlot], temps: list[TempSlot],
    learning: dict, model: BatteryModel, start_soc: float, current_temp: float,
    *,
    tariff: str, baseload_w: float, mild_w: float, cold_w: float,
    pv_discount_pct: float, efficiency_pct: float, battery_max_kw: float,
    grid_limit_kw: float, ev_now_kw: float | None, prices: dict | None,
    variant: str,
    latitude: float | None = None, longitude: float | None = None,
) -> dict:
    energy_capacity = model.estimated_chemical_capacity_kwh
    store = energy_capacity * start_soc / 100
    minimum = energy_capacity * model.minimum_soc / 100
    maximum = energy_capacity * model.maximum_soc / 100
    eta = sqrt(efficiency_pct / 100)
    utc_start = now.astimezone(timezone.utc)
    running = {key: 0.0 for key in (
        "pv_kwh", "house_kwh", "pump_kwh", "ev_kwh",
        "grid_import_kwh", "grid_export_kwh", "pv_battery_kwh",
        "battery_to_home_kwh", "without_battery_import_kwh",
    )}
    cost = no_batt_cost = 0.0
    with_price = prices is not None
    model_steps = temp_steps = 0
    max_grid_kw = 0.0
    grid_over_count = 0
    min_soc = start_soc
    hourly = []
    hour_row = None
    stop_reason = None
    completed_steps = 0
    lowlight_assumed_steps = 0
    current_soc = start_soc
    for i in range(STEPS_48H):
        at = utc_start + timedelta(minutes=i * STEP_MINUTES)
        following = at + timedelta(minutes=STEP_MINUTES)
        local = at.astimezone(WARSAW)
        fraction_hours = STEP_MINUTES / 60
        solar_raw, coverage = _slot_energy(at, following, pv_slots)
        # Do not silently invent zero PV for daylight when the provider lacks a
        # forecast. At night a missing PV slot is conservatively treated as zero.
        daylight = required_forecast(
            at if latitude is not None and longitude is not None else local,
            latitude=latitude, longitude=longitude,
            legacy_hours=(4, 22),
        )
        if coverage < 0.999 and daylight:
            stop_reason = f"Brak godzinowej prognozy PV od {local:%d.%m %H:%M}"
            break
        if coverage < 0.999:
            # Negligible low-angle sun is an explicitly reported assumption.
            lowlight_assumed_steps += 1
        solar = solar_raw * (1 - pv_discount_pct / 100)
        temp, from_weather = _temperature(at, temps, current_temp)
        temp_steps += int(from_weather)
        hp_kw = pump_power_w(temp, mild_w=mild_w, cold_w=cold_w) / 1000
        home_base_hour, from_history = _base_kwh_per_hour(
            local, learning, baseload_w, variant)
        model_steps += int(from_history)
        ev_kw = (ev_now_kw if i == 0 and ev_now_kw is not None else 0.0)
        base = home_base_hour * fraction_hours
        pump = hp_kw * fraction_hours
        ev = ev_kw * fraction_hours
        demand = base + pump + ev

        soc_before = current_soc
        direct = min(demand, solar)
        shortage = max(0., demand - direct)
        surplus = max(0., solar - direct)

        discharged = min(
            shortage, battery_max_kw * fraction_hours,
            max(0., store - minimum) * eta,
        )
        store -= discharged / eta
        imported = shortage - discharged

        charged_from_pv = min(
            surplus, battery_max_kw * fraction_hours,
            max(0., maximum - store) / eta,
        )
        store += charged_from_pv * eta
        exported = surplus - charged_from_pv
        store = max(0., min(energy_capacity, store))
        current_soc = 100 * store / energy_capacity
        min_soc = min(min_soc, current_soc)
        completed_steps += 1

        no_battery_import = max(0., demand - solar)
        zone = tariff_zone(at, tariff)
        current_price = prices.get(zone) if with_price else None
        if current_price is not None:
            cost += imported * current_price
            no_batt_cost += no_battery_import * current_price
        import_kw = imported / fraction_hours
        max_grid_kw = max(max_grid_kw, import_kw)
        if import_kw > grid_limit_kw:
            grid_over_count += 1
        increment = {
            "pv_kwh": solar, "house_kwh": demand, "pump_kwh": pump, "ev_kwh": ev,
            "grid_import_kwh": imported, "grid_export_kwh": exported,
            "pv_battery_kwh": charged_from_pv * eta,
            "battery_to_home_kwh": discharged,
            "without_battery_import_kwh": no_battery_import,
        }
        for key, value in increment.items():
            running[key] += value

        # A compact 48-row hourly graph avoids the Home Assistant Recorder
        # attribute size limit; all calculations are still on 15-min steps.
        if i % 4 == 0:
            hour_row = {
                "czas": local.strftime("%Y-%m-%d %H:%M%z"),
                "soc_od": round(soc_before, 1),
                "soc_do": None,
                "pv": 0., "dom": 0., "import": 0., "eksport": 0.,
                "auto": 0., "pompa": 0., "strefa": zone,
            }
        for field, val in (
            ("pv", solar), ("dom", demand), ("import", imported),
            ("eksport", exported), ("auto", ev), ("pompa", pump),
        ):
            hour_row[field] += val
        hour_row["soc_do"] = round(current_soc, 1)
        if i % 4 == 3:
            hourly.append(_round_data(hour_row))
            hour_row = None

    if hour_row:
        hourly.append(_round_data(hour_row))
    complete = stop_reason is None
    forecast_hours = round(completed_steps * STEP_MINUTES / 60, 2)
    quality = (
        "pelna" if complete and model_steps >= 0.9 * STEPS_48H
        and temp_steps >= 0.9 * STEPS_48H
        else "wstepna"
    )
    output = {
        "variant": variant,
        "status": "gotowa" if complete else "niepelna_prognoza_pv",
        "reason": "Symulacja 48h bez planowanego ładowania z sieci" if complete else stop_reason,
        "scenario": "bez_dodatkowego_ladowania_z_sieci",
        "forecast_hours": forecast_hours,
        "lowlight_assumed_zero_steps": lowlight_assumed_steps,
        "quality": quality,
        "training_slots": model_steps,
        "weather_slots": temp_steps,
        "current_ev_first_15min_only": bool(ev_now_kw is not None and ev_now_kw > 0),
        "future_ev_sessions_unknown": True,
        "soc_end_pct": round(current_soc, 1),
        "soc_min_pct": round(min_soc, 1),
        "grid_peak_kw": round(max_grid_kw, 2),
        "grid_over_limit_steps": grid_over_count,
        "timeline_hours": hourly,
        "cost_import_pln": round(cost, 2) if with_price else None,
        "cost_no_battery_import_pln": round(no_batt_cost, 2) if with_price else None,
        "savings_pln": None,  # Cannot compute without export settlement.
    }
    output.update({key: round(value, 2) for key, value in running.items()})
    return output


def simulate_48h(
    now: datetime, pv_slots: list[PvSlot], temps: list[TempSlot],
    learning: dict, model: BatteryModel, start_soc: float, current_temp: float,
    *,
    tariff: str, baseload_w: float = 400, mild_w: float = 600,
    cold_w: float = 1200, pv_discount_pct: float = 15,
    efficiency_pct: float = 90, battery_max_kw: float = 10,
    grid_limit_kw: float = 15, ev_now_kw: float | None = None,
    prices: dict | None = None,
    latitude: float | None = None, longitude: float | None = None,
) -> dict:
    """Produce 15-minute sequential simulations for typical and cautious use.

    Absolutely no grid-charge optimization or hardware writes. All numbers are
    projections, not measurement or realized financial savings.
    """
    if now.tzinfo is None:
        raise ValueError("Timestamp must have timezone")
    numbers = (start_soc, current_temp, baseload_w, mild_w, cold_w,
               pv_discount_pct, efficiency_pct, battery_max_kw, grid_limit_kw)
    if not all(isfinite(float(v)) for v in numbers):
        raise ValueError("Nonfinite simulation input")
    if not (0 <= start_soc <= 100 and -70 <= current_temp <= 65 and
            baseload_w >= 0 and mild_w >= 0 and cold_w >= 0 and
            0 <= pv_discount_pct <= 100 and 0 < efficiency_pct <= 100 and
            0 < battery_max_kw <= 100 and 0 < grid_limit_kw <= 100):
        raise ValueError("Invalid simulation limits")
    if ev_now_kw is not None and not (0 <= ev_now_kw <= 25):
        raise ValueError("Invalid EV load")
    if not pv_slots:
        return {"status": "brak_prognozy_pv", "reason": "Nie ma prognozy godzinowej PV",
                "forecast_hours": 0, "quality": "brak", "timeline_hours": [],
                "scenario": "bez_dodatkowego_ladowania_z_sieci"}
    typical = _calculate(
        now, pv_slots, temps, learning, model, start_soc, current_temp,
        tariff=tariff, baseload_w=baseload_w, mild_w=mild_w, cold_w=cold_w,
        pv_discount_pct=pv_discount_pct, efficiency_pct=efficiency_pct,
        battery_max_kw=battery_max_kw, grid_limit_kw=grid_limit_kw,
        ev_now_kw=ev_now_kw, prices=prices, variant="typowy",
        latitude=latitude, longitude=longitude,
    )
    cautious = _calculate(
        now, pv_slots, temps, learning, model, start_soc, current_temp,
        tariff=tariff, baseload_w=baseload_w, mild_w=mild_w, cold_w=cold_w,
        pv_discount_pct=pv_discount_pct, efficiency_pct=efficiency_pct,
        battery_max_kw=battery_max_kw, grid_limit_kw=grid_limit_kw,
        ev_now_kw=ev_now_kw, prices=prices, variant="ostrozny",
        latitude=latitude, longitude=longitude,
    )
    typical["cautious"] = {
        key: value for key, value in cautious.items()
        if key not in ("timeline_hours",)
    }
    typical["model_note"] = (
        "Symulacja, nie pomiar. Deye Load = dom + EV + pompa. "
        "Profil bazowy wyklucza EV i pompę; prognoza pompy jest dodawana raz. "
        "Nie znam przyszłych sesji EV. Ładowanie magazynu z sieci nie jest "
        "planowane ani wykonywane. Brak punktów o bardzo niskim kącie " 
        "Słońca jest szacowany jako zero i oddzielnie raportowany. " 
        "15kW to limit ostrzegawczy, a nie "
        "gwarantowana ochrona faz."
    )
    return typical
