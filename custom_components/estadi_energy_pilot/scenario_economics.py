"""Comparable read-only 48h battery scenarios and transparent energy costs.

Two strategies use identical quarter-hour PV, home, heat-pump and EV loads:
1) baseline: solar surplus / discharge but NO additional grid battery charge;
2) proposed: grid charging only during the planner's cheap window and subject
   to a conservative total-import cap. This is NOT an inverter command.

No actual savings are claimed. In particular, different terminal SOC levels
represent different energy inventories and invalidate a naive cost comparison.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt
from typing import Any

from .battery_model import BatteryModel
from .engine import PvSlot, TempSlot, pump_power_w
from .simulation_48h import _slot_energy, _temperature, _base_kwh_per_hour
from .tariffs import WARSAW, tariff_zone

STEP_H = 0.25
STEPS = 192
MAX_HORIZON_H = 48
FAIR_SOC_TOLERANCE_PP = 0.5


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        instant = value
    elif isinstance(value, str):
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return instant.astimezone(timezone.utc) if instant.tzinfo else None


def _valid_prices(prices: dict[str, float] | None, tariff: str) -> bool:
    required = {"cheap", "peak"} if tariff == "G12w" else {"cheap", "morning", "evening"}
    return (isinstance(prices, dict) and required.issubset(prices) and
            all((_float(prices.get(key)) or 0) > 0 for key in required))


def _sunlight_may_be_missing(moment: datetime, coverage: float) -> bool:
    local = moment.astimezone(WARSAW)
    summer = 4 <= local.month <= 9
    start, end = (5, 21) if summer else (7, 17)
    return coverage < .999 and start <= local.hour < end


def _evaluate(
    now: datetime, pv_slots: list[PvSlot], temps: list[TempSlot],
    learning: dict, model: BatteryModel, soc: float, temp: float, *,
    tariff: str, prices: dict[str, float] | None, export_value: float | None,
    baseload_w: float, mild_w: float, cold_w: float, pv_discount_pct: float,
    efficiency_pct: float, battery_max_kw: float, grid_limit_kw: float,
    buffer_kw: float, ev_kw: float | None, plan: dict | None,
    future_ev_stress: dict | None = None,
) -> dict:
    """Calculate one strategy with 15-minute physical energy bookkeeping."""
    store_capacity = model.estimated_chemical_capacity_kwh
    store = store_capacity * soc / 100
    floor = store_capacity * model.minimum_soc / 100
    ceiling = store_capacity * model.maximum_soc / 100
    eta = sqrt(efficiency_pct / 100)
    soft_grid_limit = grid_limit_kw - buffer_kw
    start, end, requested_kw, target_soc = None, None, None, None
    if plan is not None:
        start = _instant(plan.get("start"))
        end = _instant(plan.get("end_window"))
        requested_kw = _float(plan.get("power_kw"))
        target_soc = _float(plan.get("target_soc"))
    totals = dict(import_kwh=0., export_kwh=0., pv_kwh=0.,
                  home_kwh=0., ev_kwh=0., heat_pump_kwh=0.,
                  grid_battery_kwh=0., pv_battery_kwh=0.,
                  battery_to_load_kwh=0.)
    price_import = 0.
    price_export = 0.
    peak_grid_kw = 0.
    soft_clips = 0
    hard_limit_steps = 0
    assumed_dark_slots = 0
    trained_steps = 0
    weather_steps = 0
    rows = []
    partial_hour = None
    stop = None
    completed = 0

    for i in range(STEPS):
        at = now + timedelta(minutes=15 * i)
        next_at = at + timedelta(minutes=15)
        local = at.astimezone(WARSAW)
        raw_pv, pv_coverage = _slot_energy(at, next_at, pv_slots)
        if _sunlight_may_be_missing(at, pv_coverage):
            stop = f"Brak danych PV w godzinie {local:%d.%m %H:%M}"
            break
        if pv_coverage < .999:
            assumed_dark_slots += 1
        solar_kwh = raw_pv * (1 - pv_discount_pct / 100)
        degrees, weather_known = _temperature(at, temps, temp)
        weather_steps += int(weather_known)
        hp_kwh = STEP_H * pump_power_w(
            degrees, mild_w=mild_w, cold_w=cold_w) / 1000
        base_hour, trained = _base_kwh_per_hour(
            local, learning, baseload_w, "typowy")
        trained_steps += int(trained)
        base_kwh = base_hour * STEP_H
        # Deye Load already contains both EV and heat pump. The baseline
        # excludes both before these separate forecasts are added ONCE.
        ev_kwh = STEP_H * ev_kw if i == 0 and ev_kw is not None else 0.
        if i > 0 and future_ev_stress and future_ev_stress.get("risk_ready"):
            daytype = "weekend" if local.weekday() >= 5 else "weekday"
            hours = (future_ev_stress.get("profiles", {}).get(daytype) or {}).get(
                "p90_kwh_per_hour", [])
            if len(hours) == 24:
                historical_hour = _float(hours[local.hour])
                if historical_hour is not None and historical_hour >= 0:
                    ev_kwh = historical_hour * STEP_H
        demand = base_kwh + hp_kwh + ev_kwh
        direct = min(solar_kwh, demand)
        shortage = demand - direct
        surplus = solar_kwh - direct
        old_soc = store * 100 / store_capacity

        in_window = (
            start is not None and end is not None and
            start <= at and next_at <= end and
            tariff_zone(at, tariff) == "cheap" and
            tariff_zone(next_at - timedelta(seconds=1), tariff) == "cheap" and
            requested_kw is not None and requested_kw > 0 and
            target_soc is not None and old_soc < target_soc - .01
        )
        # During grid battery charge the battery cannot simultaneously
        # discharge to supply the home, matching the conservative advisor.
        discharged = 0. if in_window else min(
            shortage, battery_max_kw * STEP_H,
            max(0., store - floor) * eta,
        )
        store -= discharged / eta
        house_grid = shortage - discharged

        solar_battery = min(
            surplus, battery_max_kw * STEP_H,
            max(0., ceiling - store) / eta,
        )
        store += solar_battery * eta
        extra_grid_battery = 0.
        if in_window:
            space_by_soc = max(0., store_capacity * target_soc / 100 - store) / eta
            available_kw_h = max(0., soft_grid_limit * STEP_H - house_grid)
            remaining_charge_power = max(0., battery_max_kw * STEP_H - solar_battery)
            extra_grid_battery = min(
                requested_kw * STEP_H,
                available_kw_h,
                space_by_soc,
                remaining_charge_power,
            )
            if extra_grid_battery < requested_kw * STEP_H - .001 and space_by_soc > .001:
                soft_clips += 1
            store += extra_grid_battery * eta
        store = max(floor, min(ceiling, store))
        imported = house_grid + extra_grid_battery
        exported = max(0., surplus - solar_battery)
        peak_grid_kw = max(peak_grid_kw, imported / STEP_H)
        if imported / STEP_H > grid_limit_kw + 1e-6:
            hard_limit_steps += 1

        zone = tariff_zone(at, tariff)
        if prices is not None:
            price_import += imported * prices[zone]
        if export_value is not None:
            price_export += exported * export_value

        increments = dict(
            import_kwh=imported, export_kwh=exported, pv_kwh=solar_kwh,
            home_kwh=demand, ev_kwh=ev_kwh, heat_pump_kwh=hp_kwh,
            grid_battery_kwh=extra_grid_battery,
            pv_battery_kwh=solar_battery * eta,
            battery_to_load_kwh=discharged,
        )
        for key, value in increments.items():
            totals[key] += value
        completed += 1

        if i % 4 == 0:
            partial_hour = {
                "czas": local.strftime("%Y-%m-%d %H:%M%z"),
                "soc_start": round(old_soc, 1), "soc_end": None,
                "import_kwh": 0., "export_kwh": 0., "grid_battery_kwh": 0.,
                "pv_kwh": 0., "home_kwh": 0.,
            }
        for key in ("import_kwh", "export_kwh", "grid_battery_kwh",
                    "pv_kwh", "home_kwh"):
            partial_hour[key] += increments[key]
        partial_hour["soc_end"] = round(store * 100 / store_capacity, 1)
        if i % 4 == 3:
            rows.append({
                key: round(val, 3) if isinstance(val, float) else val
                for key, val in partial_hour.items()
            })
            partial_hour = None

    if partial_hour is not None:
        rows.append({key: round(val, 3) if isinstance(val, float) else val
                     for key, val in partial_hour.items()})
    result = {
        "status": "gotowy" if completed == STEPS else "niepelna_prognoza",
        "hours": round(completed * STEP_H, 2),
        "reason": stop,
        "soc_end_pct": round(store * 100 / store_capacity, 2),
        "soc_start_pct": round(soc, 2),
        "grid_peak_kw": round(peak_grid_kw, 2),
        "grid_over_limit_steps": hard_limit_steps,
        "grid_charge_clipped_steps": soft_clips,
        "pv_night_assumed_steps": assumed_dark_slots,
        "trained_steps": trained_steps,
        "weather_steps": weather_steps,
        "import_cost_pln": round(price_import, 2) if prices is not None and completed == STEPS else None,
        "export_credit_pln": round(price_export, 2) if export_value is not None and completed == STEPS else None,
        "timeline_4h": [rows[k] for k in range(3, len(rows), 4)],
    }
    result.update({key: round(value, 2) for key, value in totals.items()})
    if prices is not None and export_value is not None and completed == STEPS:
        result["estimated_energy_balance_pln"] = round(price_import - price_export, 2)
    else:
        result["estimated_energy_balance_pln"] = None
    return result


def compare_scenarios(
    *, now: datetime, pv_slots: list[PvSlot], temperatures: list[TempSlot],
    learning: dict, model: BatteryModel, soc: float, current_temp: float,
    tariff: str, prices: dict[str, float] | None,
    proposed_plan: dict | None, export_value_pln_kwh: float | None,
    baseload_w: float, mild_w: float, cold_w: float, pv_discount_pct: float,
    efficiency_pct: float, battery_max_kw: float, grid_limit_kw: float,
    grid_buffer_kw: float, ev_now_kw: float | None,
    future_ev_stress: dict | None = None,
) -> dict:
    """Return two directly comparable forecasts, or explicit missing inputs.

    We DO NOT call this 'savings' when end SOC differs, export compensation
    is unknown or future EV sessions have not been scheduled.
    """
    at = _instant(now)
    if at is None:
        raise ValueError("Timezone-aware now required")
    if tariff not in ("G12w", "G13"):
        raise ValueError("Unsupported tariff")
    vals = [soc, current_temp, baseload_w, mild_w, cold_w, pv_discount_pct,
            efficiency_pct, battery_max_kw, grid_limit_kw, grid_buffer_kw]
    if any(_float(v) is None for v in vals):
        raise ValueError("Non-finite simulation input")
    if (not model.minimum_soc <= soc <= model.maximum_soc or
            not -70 <= current_temp <= 65 or
            min(baseload_w, mild_w, cold_w) < 0 or
            not 0 <= pv_discount_pct <= 100 or
            not 0 < efficiency_pct <= 100 or
            not 0 < battery_max_kw <= 100 or
            not 0 < grid_limit_kw <= 100 or
            not 0 <= grid_buffer_kw < grid_limit_kw):
        raise ValueError("Invalid physical limits")
    if ev_now_kw is not None and not 0 <= ev_now_kw <= 25:
        raise ValueError("Invalid EV power")
    if export_value_pln_kwh is not None and not 0 < export_value_pln_kwh <= 10:
        raise ValueError("Invalid export compensation")
    if prices is not None and not _valid_prices(prices, tariff):
        raise ValueError("Invalid import tariff price set")

    if not pv_slots:
        return {
            "status": "brak_prognozy_pv", "reason": "Brak prognozy PV na kolejne godziny",
            "savings_pln": None, "plan_written_to_deye": False,
        }
    if not _valid_prices(prices, tariff):
        prices = None
    plan = proposed_plan or {}
    if plan.get("status") == "wstepny_plan":
        start = _instant(plan.get("start"))
        end = _instant(plan.get("end_window"))
        power = _float(plan.get("power_kw"))
        target = _float(plan.get("target_soc"))
        if (start is None or end is None or
                not at <= start < end <= at + timedelta(hours=48) or
                power is None or not 0 < power <= battery_max_kw or
                target is None or not model.minimum_soc <= target <= model.maximum_soc):
            return {
                "status": "bledny_plan",
                "reason": "Plan ma niepoprawny czas, moc lub SOC docelowy",
                "savings_pln": None, "plan_written_to_deye": False,
            }
        with_plan = plan
    else:
        with_plan = None

    common = dict(
        now=at, pv_slots=pv_slots, temps=temperatures, learning=learning,
        model=model, soc=soc, temp=current_temp, tariff=tariff,
        prices=prices, export_value=export_value_pln_kwh,
        baseload_w=baseload_w, mild_w=mild_w, cold_w=cold_w,
        pv_discount_pct=pv_discount_pct, efficiency_pct=efficiency_pct,
        battery_max_kw=battery_max_kw, grid_limit_kw=grid_limit_kw,
        buffer_kw=grid_buffer_kw, ev_kw=ev_now_kw,
    )
    baseline = _evaluate(**common, plan=None)
    projected = _evaluate(**common, plan=with_plan) if with_plan else None
    # Separate stress calculation: NEVER silently mix hypothetical historical
    # EV sessions into the normal base scenario or planner commands.
    stress = None
    if future_ev_stress and future_ev_stress.get("risk_ready"):
        stress_base = _evaluate(**common, plan=None, future_ev_stress=future_ev_stress)
        stress_plan = (_evaluate(**common, plan=with_plan, future_ev_stress=future_ev_stress)
                       if with_plan else None)
        stress = {
            "status": "gotowy_scenariusz_stresowy" if stress_base["status"] == "gotowy"
            and (stress_plan is None or stress_plan["status"] == "gotowy")
            else "niepelne_dane",
            "baseline": {
                key: stress_base.get(key) for key in (
                    "status", "hours", "ev_kwh", "home_kwh", "import_kwh",
                    "import_cost_pln", "soc_end_pct", "grid_peak_kw",
                    "grid_over_limit_steps",
                )
            },
            "plan": {
                key: stress_plan.get(key) for key in (
                    "status", "hours", "ev_kwh", "home_kwh", "import_kwh",
                    "import_cost_pln", "soc_end_pct", "grid_peak_kw",
                    "grid_over_limit_steps", "grid_charge_clipped_steps",
                )
            } if stress_plan is not None else None,
            "estimated_savings_pln": None,
            "future_ev_sessions_confirmed": False,
            "warning": future_ev_stress.get("warning"),
        }

    incomplete = baseline["status"] != "gotowy" or (
        projected is not None and projected["status"] != "gotowy"
    )
    terminal_diff = (
        round(projected["soc_end_pct"] - baseline["soc_end_pct"], 2)
        if projected is not None else None
    )
    price_diff = (
        round(projected["import_cost_pln"] - baseline["import_cost_pln"], 2)
        if projected is not None and projected["import_cost_pln"] is not None
        and baseline["import_cost_pln"] is not None else None
    )
    estimate_diff = (
        round(baseline["estimated_energy_balance_pln"] -
              projected["estimated_energy_balance_pln"], 2)
        if projected is not None and projected["estimated_energy_balance_pln"] is not None
        and baseline["estimated_energy_balance_pln"] is not None else None
    )
    same_energy = terminal_diff is not None and abs(terminal_diff) <= FAIR_SOC_TOLERANCE_PP
    # Even when end SOC is equal, future EV sessions, exact settlement and
    # device response are not confirmed. Never call it a realized saving.
    fair_estimate = estimate_diff if same_energy and not incomplete else None
    if incomplete:
        status = "niepelna_prognoza"
        reason = "Niepełne dane PV — nie porównujemy kosztów niepełnej prognozy"
    elif projected is None:
        status = "brak_planu"
        reason = "Brak wykonalnego planu ładowania, pokazano tylko scenariusz bazowy"
    elif prices is None:
        status = "brak_cen_importu"
        reason = "Wprowadź faktyczne ceny zakupu dla wszystkich stref"
    elif export_value_pln_kwh is None:
        status = "brak_wartosci_eksportu"
        reason = "Nie podano szacunkowej wartości eksportu; porównanie kosztu importu nie obejmuje eksportu"
    elif not same_energy:
        status = "rozny_soc_koncowy"
        reason = "Scenariusze kończą z innym SOC — różnica rachunku nie jest czystą oszczędnością"
    else:
        status = "porownanie_wstepne"
        reason = "Warianty kończą z podobnym SOC; wynik jest prognozą przy przyjętych cenach, nie zrealizowaną oszczędnością"
    return {
        "status": status, "reason": reason,
        "baseline": baseline, "plan": projected,
        "with_grid_charging": projected is not None,
        "tariff": tariff, "import_prices_confirmed": prices is not None,
        "export_price_confirmed": export_value_pln_kwh is not None,
        "export_value_pln_kwh": export_value_pln_kwh,
        "horizon_h": baseline["hours"],
        "import_cost_delta_pln": price_diff,
        "estimated_balance_advantage_pln": fair_estimate,
        "unadjusted_balance_difference_pln": estimate_diff,
        "terminal_soc_difference_pp": terminal_diff,
        "savings_pln": None,
        "realized_savings_pln": None,
        "future_ev_unknown": True,
        "ev_stress": stress,
        "plan_written_to_deye": False,
        "phase_safety_not_verified": True,
        "note": (
            "Prognozy wariantów bez zapisu do Deye. Koszty importu zależą od "
            "cen wpisanych przez użytkownika, a wartość eksportu od uproszczonej "
            "stawki szacunkowej — to nie pełne rozliczenie net-billingu. "
            "Brak przyszłego harmonogramu EV i nieznany rzeczywisty BMS. "
            "Zmienny SOC końcowy oznacza różną energię pozostającą w magazynie."
        ),
    }
