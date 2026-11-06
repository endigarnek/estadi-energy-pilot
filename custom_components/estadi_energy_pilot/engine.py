"""Pure Python forecast and battery target calculations for ESTADI Energy Pilot.

No Home Assistant imports: this module can be unit-tested without HA installed.
The model is advisory and never controls a battery directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time, date
from math import ceil, isfinite
from typing import Any, Iterable


@dataclass(frozen=True)
class PvSlot:
    start: datetime
    power_kw: float
    duration_minutes: int = 30


@dataclass(frozen=True)
class TempSlot:
    start: datetime
    degrees_c: float


@dataclass(frozen=True)
class Plan:
    name: str
    start: datetime
    end: datetime
    pv_kwh: float
    load_kwh: float
    heat_kwh: float
    grid_gap_kwh: float
    target_soc: int
    can_calculate: bool
    reason: str


def _as_positive_number(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if isfinite(num) and num >= 0 else None


def parse_pv_slots(*forecast_attributes: Any) -> list[PvSlot]:
    """Parse Solcast daily sensor detailedForecast or detailedHourly entries.

    Values are forecast average kW, not kWh. period_start is ISO timestamp.
    Unavailable or malformed entries are ignored. Duplicate timestamps deduped.
    """
    merged: dict[datetime, PvSlot] = {}
    for attr in forecast_attributes:
        if not isinstance(attr, dict):
            continue
        detail = attr.get("detailedForecast")
        duration = 30
        if not isinstance(detail, list) or not detail:
            detail = attr.get("detailedHourly")
            duration = 60
        if not isinstance(detail, list):
            continue
        for row in detail:
            if not isinstance(row, dict):
                continue
            try:
                dt = datetime.fromisoformat(str(row["period_start"]).replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                continue
            if dt.tzinfo is None:
                continue
            kw = _as_positive_number(row.get("pv_estimate"))
            if kw is None:
                continue
            merged[dt] = PvSlot(dt, kw, duration)
    return sorted(merged.values(), key=lambda s: s.start)


def parse_weather_slots(forecasts: Any) -> list[TempSlot]:
    result = []
    if not isinstance(forecasts, list):
        return result
    for row in forecasts:
        if not isinstance(row, dict):
            continue
        try:
            dt = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
            temp = float(row["temperature"])
        except (KeyError, ValueError, TypeError):
            continue
        if dt.tzinfo is not None and isfinite(temp):
            result.append(TempSlot(dt, temp))
    return sorted(result, key=lambda t: t.start)


def pump_power_w(temp_c: float, threshold_c: float = 8.0,
                 mild_w: float = 600.0, cold_w: float = 1200.0,
                 cold_temp_c: float = -5.0) -> float:
    """Expected mean heat-pump electrical consumption at an outdoor temperature."""
    if temp_c >= threshold_c:
        return 0.0
    if temp_c <= cold_temp_c:
        return cold_w
    ratio = (threshold_c - temp_c) / (threshold_c - cold_temp_c)
    return mild_w + ratio * (cold_w - mild_w)


def _temperature_at(at: datetime, temp_slots: list[TempSlot], fallback: float) -> float:
    """Use most recent weather hourly prediction, otherwise current temp."""
    candidates = [t.degrees_c for t in temp_slots if t.start <= at]
    return candidates[-1] if candidates else fallback


def _overlap_hours(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    begin, end = max(a0, b0), min(a1, b1)
    return max(0.0, (end - begin).total_seconds() / 3600)


def _make_window(day: date, start_hour: int, end_hour: int, tzinfo) -> tuple[datetime, datetime]:
    return (datetime.combine(day, time(start_hour), tzinfo=tzinfo),
            datetime.combine(day, time(end_hour), tzinfo=tzinfo))


def upcoming_windows(now: datetime, night_end: int = 7,
                     afternoon_end: int = 16, expensive_end: int = 21,
                     midday_start: int = 13) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime]]:
    """Expensive periods after the cheap nighttime and afternoon windows."""
    if now.tzinfo is None:
        raise ValueError("now needs a timezone")
    night_day = now.date() if now.hour < night_end else now.date() + timedelta(days=1)
    afternoon_day = now.date() if now.hour < afternoon_end else now.date() + timedelta(days=1)
    return (_make_window(night_day, night_end, midday_start, now.tzinfo),
            _make_window(afternoon_day, afternoon_end, expensive_end, now.tzinfo))


def plan_window(name: str, start: datetime, end: datetime, pv: list[PvSlot],
                temps: list[TempSlot], current_temp: float, capacity_kwh: float,
                baseload_w: float, reserve_soc: int, max_soc: int,
                pv_discount_pct: int, efficiency_pct: int,
                margin_kwh: float, mild_w: float, cold_w: float) -> Plan:
    """Compute conservative SOC target for the start of an expensive period.

    Negative net energy within one slot can charge the battery. A net surplus
    does not offset future deficits in this conservative version.
    """
    if capacity_kwh <= 0 or start >= end:
        return Plan(name, start, end, 0, 0, 0, 0, reserve_soc, False, "Nieprawidłowa konfiguracja")
    time_step = timedelta(minutes=30)
    pv_kwh = load_kwh = heat_kwh = gap_kwh = 0.0
    cursor = start
    while cursor < end:
        following = min(cursor + time_step, end)
        hours = (following - cursor).total_seconds() / 3600
        temp = _temperature_at(cursor, temps, current_temp)
        pump_w = pump_power_w(temp, mild_w=mild_w, cold_w=cold_w)
        heat = hours * pump_w / 1000
        load = hours * (baseload_w + pump_w) / 1000
        solar = sum(slot.power_kw * _overlap_hours(cursor, following, slot.start,
                          slot.start + timedelta(minutes=slot.duration_minutes)) for slot in pv)
        solar *= (100 - pv_discount_pct) / 100
        pv_kwh += solar
        load_kwh += load
        heat_kwh += heat
        gap_kwh += max(0.0, load - solar)
        cursor = following

    # Missing forecast must never be treated as predicted zero production.
    solar_day_available = any(slot.start.date() == start.date() for slot in pv)
    if not solar_day_available:
        return Plan(name, start, end, round(pv_kwh, 2), round(load_kwh, 2),
                    round(heat_kwh, 2), round(gap_kwh, 2), reserve_soc, False,
                    "Brak godzinowej prognozy PV na ten dzień")
    required = capacity_kwh * reserve_soc / 100 + gap_kwh / (efficiency_pct / 100) + margin_kwh
    target = max(reserve_soc, min(max_soc, ceil(100 * required / capacity_kwh)))
    reason = ("Cel ograniczony maksymalnym SOC" if required > capacity_kwh * max_soc / 100
              else "Prognoza dostępna — obliczono bezpieczny cel SOC")
    return Plan(name, start, end, round(pv_kwh, 2), round(load_kwh, 2),
                round(heat_kwh, 2), round(gap_kwh, 2), target, True, reason)


def cheap_window(now: datetime, night_start: int = 21, night_end: int = 7,
                 midday_start: int = 13, afternoon_end: int = 16) -> str | None:
    hour = now.hour + now.minute / 60
    if hour >= night_start or hour < night_end:
        return "night"
    if midday_start <= hour < afternoon_end:
        return "afternoon"
    return None


def get_all_plans(now: datetime, pv_attrs: Iterable[Any], temps: list[TempSlot],
                  current_temp: float, soc: float, capacity_kwh: float,
                  baseload_w: float = 400, reserve_soc: int = 20,
                  max_soc: int = 95, pv_discount_pct: int = 15,
                  efficiency_pct: int = 90, margin_kwh: float = 1,
                  mild_w: float = 600, cold_w: float = 1200,
                  night_start: int = 21, night_end: int = 7,
                  midday_start: int = 13, afternoon_end: int = 16,
                  pv_slots: list[PvSlot] | None = None) -> dict[str, Any]:
    slots = parse_pv_slots(*pv_attrs) if pv_slots is None else pv_slots
    night_window, afternoon_window = upcoming_windows(
        now, night_end, afternoon_end, night_start, midday_start)
    parameters = dict(pv=slots, temps=temps, current_temp=current_temp,
                      capacity_kwh=capacity_kwh, baseload_w=baseload_w,
                      reserve_soc=reserve_soc, max_soc=max_soc,
                      pv_discount_pct=pv_discount_pct, efficiency_pct=efficiency_pct,
                      margin_kwh=margin_kwh, mild_w=mild_w, cold_w=cold_w)
    night = plan_window("night", *night_window, **parameters)
    afternoon = plan_window("afternoon", *afternoon_window, **parameters)
    window = cheap_window(now, night_start, night_end, midday_start, afternoon_end)
    selected = night if window == "night" else afternoon if window == "afternoon" else None
    amount = (max(0.0, (selected.target_soc - soc) / 100 * capacity_kwh / (efficiency_pct / 100))
              if selected and selected.can_calculate else 0.0)
    return {"night": night, "afternoon": afternoon, "charge_window": window,
            "charge_needed_kwh": round(amount, 2),
            "recommended": bool(selected and selected.can_calculate and amount >= 0.2),
            "forecast_intervals": len(slots)}
