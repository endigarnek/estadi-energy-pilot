"""Non-EV household consumption learning from actual HA hourly history.

Builds conservative hourly P50/P90 without guessing whether Deye Load includes
car charging: exclude every hour with detected EV activity. This is not yet a
temperature-aware heat-pump model. All values are kWh per hour.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from math import ceil
from statistics import median

from .tariffs import is_day_off

MIN_DAYS = 7
MAX_DAYS = 30
MIN_HOURLY_COVERAGE = 0.9


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    items = sorted(values)
    pos = (len(items) - 1) * fraction
    i = int(pos)
    if i == len(items) - 1:
        return items[i]
    return items[i] + (items[i + 1] - items[i]) * (pos - i)


def build_household_profile(history_days: dict, today: date, *, min_days: int = MIN_DAYS) -> dict:
    samples: dict[tuple[bool, int], list[float]] = {}
    common: dict[int, list[float]] = {}
    complete_days = 0
    ev_skipped_hours = 0
    for key in sorted(history_days, reverse=True):
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        if day >= today or (today - day).days > MAX_DAYS:
            continue
        row = history_days.get(key) or {}
        actual, coverage = row.get("actual", {}), row.get("coverage", {})
        ch, ev = actual.get("home", {}), actual.get("ev", {})
        hcov, ecov = coverage.get("home", {}), coverage.get("ev", {})
        if sum(hcov.values()) < 21.6 or sum(ecov.values()) < 21.6:
            continue
        complete_days += 1
        off = is_day_off(day)
        for hour in range(24):
            slot = f"{hour:02}:00"
            if hcov.get(slot, 0) < MIN_HOURLY_COVERAGE or ecov.get(slot, 0) < MIN_HOURLY_COVERAGE:
                continue
            amount, ev_energy = ch.get(slot), ev.get(slot)
            if amount is None or ev_energy is None or amount < 0 or ev_energy < 0:
                continue
            if ev_energy >= 0.1:
                ev_skipped_hours += 1
                continue
            samples.setdefault((off, hour), []).append(amount)
            common.setdefault(hour, []).append(amount)
        if complete_days >= MAX_DAYS:
            break

    ready = complete_days >= min_days
    by_kind = {}
    for kind in (False, True):
        for hour in range(24):
            values = samples.get((kind, hour), [])
            if len(values) < 3:
                values = common.get(hour, [])
            if len(values) < 3:
                continue
            by_kind[f"{'weekend' if kind else 'weekday'}_{hour:02}"] = {
                "p50_kwh": round(median(values), 3),
                "p90_kwh": round(percentile(values, 0.9), 3),
                "sample_count": len(values),
            }
    return {
        "status": "gotowy" if ready and len(by_kind) >= 24 else "uczy_sie",
        "days_complete": complete_days,
        "minimum_days": min_days,
        "ev_hours_excluded": ev_skipped_hours,
        "hourly": by_kind,
        "limitations": "P50/P90 z godzin bez EV; pompa i urządzenia są w zmierzonej mocy domu; brak korekty temperatury",
    }


def next_24h_profile(profile: dict, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("timezone required")
    if profile["status"] != "gotowy":
        return {"available": False, "hours": [], "total_p50_kwh": None, "total_p90_kwh": None}
    # Step in absolute time to avoid losing repeated hours on DST transition.
    from datetime import timezone
    utc = now.astimezone(timezone.utc)
    cursor = utc.replace(minute=0, second=0, microsecond=0)
    if cursor < utc:
        cursor += timedelta(hours=1)
    rows = []
    for i in range(24):
        at = (cursor + timedelta(hours=i)).astimezone(now.tzinfo)
        kind = "weekend" if is_day_off(at.date()) else "weekday"
        slot = profile["hourly"].get(f"{kind}_{at.hour:02}")
        rows.append({"time": at.isoformat(), "p50_kwh": slot.get("p50_kwh") if slot else None,
                     "p90_kwh": slot.get("p90_kwh") if slot else None})
    complete = all(row["p50_kwh"] is not None for row in rows)
    return {
        "available": complete,
        "hours": rows,
        "total_p50_kwh": round(sum(r["p50_kwh"] for r in rows), 2) if complete else None,
        "total_p90_kwh": round(sum(r["p90_kwh"] for r in rows), 2) if complete else None,
    }
