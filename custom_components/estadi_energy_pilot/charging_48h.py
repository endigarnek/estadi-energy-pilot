"""Read-only 48h charging window optimizer with a 15 kW connection constraint.

This module generates *advice*; it does not write HA services or Deye registers.
Unknown phase currents, future EV sessions and BMS charge limits prevent using
these recommendations as automatic power commands.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt

from .battery_model import BatteryModel
from .engine import PvSlot, TempSlot, pump_power_w
from .simulation_48h import _slot_energy, _temperature, _base_kwh_per_hour
from .tariffs import tariff_zone, WARSAW

STEP = timedelta(minutes=15)
MIN_RECOMMENDED_KW = 3.0
MAX_FORECAST_STEPS = 192


def _result(status: str, reason: str, **values) -> dict:
    return {
        "status": status,
        "reason": reason,
        "hardware_control": False,
        "phase_limits_verified": False,
        "future_ev_schedule_verified": False,
        "approach": "tylko_doradztwo",
        **values,
    }


def _solar_complete(at: datetime, coverage: float) -> bool:
    """Fail closed on missing forecast during plausibly sunlit hours.

    Unlike a zero nighttime forecast, missing daytime forecast cannot be
    interpreted as no PV. Uses deliberately broad seasonal daylight bounds.
    """
    local = at.astimezone(WARSAW)
    summer = 4 <= local.month <= 9
    first, last = (5, 21) if summer else (7, 17)
    return coverage >= 0.999 or not first <= local.hour < last


def recommend_charge(
    *,
    now: datetime,
    window: tuple[datetime, datetime] | None,
    soc: float | None,
    target_soc: float | None,
    model: BatteryModel,
    pv_slots: list[PvSlot],
    temperatures: list[TempSlot],
    learning: dict,
    current_temp: float,
    tariff: str,
    baseload_w: float,
    mild_w: float,
    cold_w: float,
    pv_discount_pct: float,
    efficiency_pct: float,
    battery_max_kw: float,
    grid_limit_kw: float,
    grid_buffer_kw: float,
    preferred_kw: float,
    ev_now_kw: float | None,
    prices: dict[str, float] | None = None,
) -> dict:
    """Choose feasible start and power; conservatively keep active EV on.

    Target SOC is ALREADY corrected by user slider upstream, exactly once.
    All schedules are provisional and must never be sent to inverter.
    """
    if window is None:
        return _result("brak_okna", "Nie znam najbliższego okna taniej energii")
    if soc is None or target_soc is None:
        return _result("brak_soc", "Brak SOC lub celu")
    if now.tzinfo is None or any(x.tzinfo is None for x in window):
        return _result("blad_czasu", "Brak strefy czasowej")
    values = (soc, target_soc, current_temp, baseload_w, mild_w, cold_w,
              pv_discount_pct, efficiency_pct, battery_max_kw, grid_limit_kw,
              grid_buffer_kw, preferred_kw)
    if not all(isfinite(float(v)) for v in values):
        return _result("bledne_parametry", "Nieliczbowe parametry symulacji")
    if not (0 <= soc <= 100 and model.minimum_soc <= target_soc <= model.maximum_soc
            and -70 <= current_temp <= 65 and 0 <= baseload_w and
            0 <= mild_w and 0 <= cold_w and 0 <= pv_discount_pct <= 100
            and 0 < efficiency_pct <= 100 and 0 < battery_max_kw <= 100
            and 0 < grid_limit_kw <= 100 and 0 <= grid_buffer_kw < grid_limit_kw
            and 0 < preferred_kw <= battery_max_kw):
        return _result("bledne_parametry", "Niedozwolony SOC, limit lub sprawność")
    if ev_now_kw is not None and not (isfinite(ev_now_kw) and 0 <= ev_now_kw <= 25):
        return _result("bledne_EV", "Nieprawidłowa moc ładowarki EV")
    if prices is not None and not all(isfinite(v) and v > 0 for v in prices.values()):
        return _result("bledne_ceny", "Ceny energii nie są potwierdzone")

    start_utc, end_utc = (x.astimezone(timezone.utc) for x in window)
    current = now.astimezone(timezone.utc)
    if end_utc <= current or end_utc <= start_utc:
        return _result("poza_oknem", "Tanie okno już się skończyło")
    if (end_utc - current).total_seconds() > 48 * 3600:
        return _result("poza_horyzontem", "Okno kończy się poza prognozą 48 godzin")
    steps = []
    energy_capacity = model.estimated_chemical_capacity_kwh
    minimum = energy_capacity * model.minimum_soc / 100
    maximum = energy_capacity * model.maximum_soc / 100
    initial = energy_capacity * soc / 100
    eta = sqrt(efficiency_pct / 100)
    soft_limit = grid_limit_kw - grid_buffer_kw
    # Snap to the next quarter-hour if called between periods, so no
    # recommended slot crosses a cheap/expensive boundary.
    current = current.replace(second=0, microsecond=0)
    if current < now.astimezone(timezone.utc):
        current += timedelta(minutes=1)
    if current.minute % 15:
        current += timedelta(minutes=15 - current.minute % 15)
    for i in range(min(MAX_FORECAST_STEPS, int((end_utc - current).total_seconds() // 900))):
        at = current + i * STEP
        until = at + STEP
        if until > end_utc:
            break
        solar, coverage = _slot_energy(at, until, pv_slots)
        if not _solar_complete(at, coverage):
            return _result("brak_prognozy_pv",
                           "Niepełna prognoza PV w czasie planowanego ładowania",
                           brakujaca_godzina=at.astimezone(WARSAW).isoformat())
        temp, _ = _temperature(at, temperatures, current_temp)
        base_kwh, measured = _base_kwh_per_hour(
            at.astimezone(WARSAW), learning, baseload_w, "ostrozny")
        hp_kw = pump_power_w(temp, mild_w=mild_w, cold_w=cold_w) / 1000
        # For safety, an EV charging NOW may continue for the whole window.
        # Recompute after it stops (coordinator refresh). If it is currently
        # absent, future sessions are unknown and recorded as such.
        ev_kw = ev_now_kw if ev_now_kw is not None else 0.0
        demand = (base_kwh + hp_kw) * 0.25 + ev_kw * 0.25
        supply = solar * (1 - pv_discount_pct / 100)
        eligible = (at >= start_utc and
                    tariff_zone(at, tariff) == "cheap" and
                    tariff_zone(until - timedelta(seconds=1), tariff) == "cheap" and
                    until <= end_utc - STEP)
        steps.append({
            "at": at, "eligible": eligible, "solar": supply,
            "demand": demand, "trained": measured,
        })

    if not steps:
        return _result("brak_czasu", "Brak pełnych przedziałów ładowania")
    allowed = [i for i, step in enumerate(steps) if step["eligible"]]
    if not allowed:
        return _result("brak_czasu", "Brak pełnych 15-minutowych slotów z buforem")
    if not pv_slots:
        return _result("brak_prognozy_pv", "Brak prognozy fotowoltaiki")

    def evaluate(start_index: int | None, requested_kw: float) -> dict:
        energy = initial
        import_grid = charge_grid = 0.0
        cost = 0.0
        max_import = 0.0
        over_hard = 0
        charged_steps = 0
        reached = None
        grid_limit_clips = 0
        for i, slot in enumerate(steps):
            energy_before = energy
            net = slot["demand"] - slot["solar"]
            shortage = max(0.0, net)
            surplus = max(0.0, -net)
            active = (start_index is not None and i >= start_index and
                      slot["eligible"] and energy < maximum - 0.00001)
            if active:
                used_batt = 0.0
                consumed_from_grid = shortage
            else:
                used_batt = min(shortage, battery_max_kw * .25,
                                max(0.0, energy - minimum) * eta)
                energy -= used_batt / eta
                consumed_from_grid = shortage - used_batt
            power_spare = max(0., battery_max_kw * .25)
            pv_to_battery = min(surplus, power_spare,
                                max(0., maximum - energy) / eta)
            energy += pv_to_battery * eta
            power_spare -= pv_to_battery
            charged_from_grid = 0.0
            if active:
                import_budget = max(0., soft_limit * .25 - consumed_from_grid)
                requested = min(requested_kw * .25, import_budget,
                                power_spare, max(0., maximum - energy) / eta)
                charged_from_grid = max(0., requested)
                if requested_kw * .25 > import_budget + 0.001:
                    grid_limit_clips += 1
                energy += charged_from_grid * eta
                charge_grid += charged_from_grid
                if charged_from_grid > 0.001:
                    charged_steps += 1
            energy = min(maximum, energy)
            grid = consumed_from_grid + charged_from_grid
            import_grid += grid
            max_import = max(max_import, grid * 4)
            over_hard += int(grid * 4 > grid_limit_kw + 0.001)
            if prices is not None:
                cost += grid * prices[tariff_zone(slot["at"], tariff)]
            # Keep the most recent upward crossing. Earlier PV may achieve
            # the goal temporarily before the evening load drains the store.
            threshold = energy_capacity * target_soc / 100
            if energy_before < threshold - 0.001 and energy >= threshold - 0.001:
                reached = (slot["at"] + STEP).astimezone(WARSAW).isoformat()
        return {
            "end_soc": 100 * energy / energy_capacity,
            "charge_grid_kwh": charge_grid,
            "import_kwh": import_grid,
            "cost_pln": cost if prices is not None else None,
            "grid_peak_kw": max_import,
            "over_hard_steps": over_hard,
            "grid_limit_clips": grid_limit_clips,
            "charged_steps": charged_steps,
            "effective_charge_kw_avg": charge_grid / (charged_steps * 0.25) if charged_steps else 0.,
            "reached": reached,
        }

    baseline = evaluate(None, 0.0)
    if baseline["end_soc"] >= target_soc - 0.05:
        return _result(
            "bez_ladowania", "Prognoza PV i obecny SOC wystarczą do celu",
            target_soc=round(target_soc, 1), end_soc=round(baseline["end_soc"], 1),
            grid_charge_kwh=0.0, start=None, power_kw=0.0,
            initial_soc=round(soc, 1), ev_assumed_kw=ev_now_kw,
            soft_limit_kw=soft_limit, tariff=tariff,
        )

    powers = sorted({float(preferred_kw), float(battery_max_kw),
                     *[float(x) for x in range(3, 11)]})
    powers = [p for p in powers if MIN_RECOMMENDED_KW <= p <= battery_max_kw]
    candidates = []
    for power in powers:
        for first in allowed:
            projected = evaluate(first, power)
            if projected["end_soc"] < target_soc - 0.05:
                continue
            if projected["over_hard_steps"]:
                continue
            # Prefer reasonable power and lower purchased kWh; no price
            # invented when unknown. Grid cap clipping hurts reliability.
            score = (projected["charge_grid_kwh"] +
                     0.08 * abs(power - preferred_kw) +
                     0.02 * max(0., power - preferred_kw) ** 2 +
                     0.03 * projected["grid_limit_clips"] +
                     0.0002 * (len(steps) - first))
            if prices is not None:
                score += projected["cost_pln"]
            candidates.append((score, power, first, projected))
    if not candidates:
        max_possible = max((evaluate(allowed[0], battery_max_kw)["end_soc"],
                            baseline["end_soc"]))
        return _result(
            "nieosiagalny", "Cel SOC nieosiągalny w taniej strefie przy limicie przyłącza",
            target_soc=round(target_soc, 1),
            max_soc_estimate=round(max_possible, 1),
            soft_limit_kw=soft_limit, tariff=tariff,
            ev_assumed_kw=ev_now_kw,
        )
    candidates.sort(key=lambda x: x[0])
    _, power, first, chosen = candidates[0]
    start = steps[first]["at"].astimezone(WARSAW).isoformat()
    end = (steps[-1]["at"] + STEP).astimezone(WARSAW).isoformat()
    alternative = []
    for _, p, idx, row in candidates:
        if p in [x["moc_kw"] for x in alternative]:
            continue
        alternative.append({
            "moc_kw": round(p, 1),
            "start": steps[idx]["at"].astimezone(WARSAW).isoformat(),
            "koniec_przewidywany": row["reached"],
            "energia_z_sieci_kwh": round(row["charge_grid_kwh"], 2),
        })
        if len(alternative) >= 4:
            break

    return _result(
        "wstepny_plan",
        "Zalecenie warunkowe: brak potwierdzenia faz, BMS i przyszłych sesji EV",
        start=start, end_window=end, finish_estimated=chosen["reached"],
        power_kw=round(power, 2), target_soc=round(target_soc, 1),
        initial_soc=round(soc, 1), end_soc=round(chosen["end_soc"], 1),
        grid_charge_kwh=round(chosen["charge_grid_kwh"], 2),
        extra_grid_kwh=round(chosen["import_kwh"] - baseline["import_kwh"], 2),
        grid_peak_kw=round(chosen["grid_peak_kw"], 2),
        effective_charge_kw_avg=round(chosen["effective_charge_kw_avg"], 2),
        grid_charge_limited_steps=chosen["grid_limit_clips"],
        soft_limit_kw=round(soft_limit, 2),
        connection_limit_kw=round(grid_limit_kw, 2),
        ev_assumed_kw=ev_now_kw,
        trained_steps=sum(s["trained"] for s in steps),
        forecast_steps=len(steps),
        tariff=tariff,
        cost_pln=round(chosen["cost_pln"], 2) if prices is not None else None,
        alternatives=alternative,
        limitations=[
            "Przyłącze 15 kW — prognoza, nie zabezpieczenie sprzętowe",
            "Nie znam potwierdzonych limitów prądu na trzech fazach",
            "Nie znam przyszłego harmonogramu EV; aktywne EV liczę do końca okna",
            "Brak zweryfikowanych zapisów Deye/limitów BMS",
            "Docelowy SOC pochodzi jeszcze z uproszczonego modelu taryfowego",
        ],
    )
