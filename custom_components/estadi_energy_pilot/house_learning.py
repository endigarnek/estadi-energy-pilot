"""Learn household electricity demand from historical power-derived hourly energy.

Confirmed wiring of this home: Deye Load includes all household consumption,
the heat pump, and EV charging. Missing measurements are not invented as zero.
"""
from __future__ import annotations

from datetime import date
from math import ceil
from statistics import median
from typing import Any

MIN_COMPLETE_DAYS = 7
MIN_COVERAGE_PER_HOUR = 0.90
MAX_TRAINING_DAYS = 30


def resolve_ev_topology(value: str | None) -> str:
    """This user's confirmed wiring replaces earlier 'unknown' choices.

    Preserve a deliberately selected 'excluded' if hardware is changed later.
    """
    return value if value in ("included", "excluded") else "included"


def _pctl(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(len(ordered) * percentile) - 1))
    return ordered[index]


def _valid_hour(day: dict, channel: str, hour: str) -> float | None:
    amount = day.get("actual", {}).get(channel, {}).get(hour)
    coverage = day.get("coverage", {}).get(channel, {}).get(hour, 0)
    if not isinstance(amount, (int, float)) or not isinstance(coverage, (int, float)):
        return None
    if coverage < MIN_COVERAGE_PER_HOUR or amount < 0:
        return None
    return float(amount)


def _profile(rows: list[tuple[date, list[float | None], list[float | None]]],
             column: int) -> dict:
    output = {}
    for kind in ("weekday", "weekend"):
        matching = [row for row in rows if (row[0].weekday() >= 5) == (kind == "weekend")]
        series = []
        for hour in range(24):
            values = [row[column][hour] for row in matching
                      if row[column][hour] is not None]
            series.append({
                "hour": f"{hour:02}:00",
                "p50_kwh": round(median(values), 3) if values else None,
                "p90_kwh": round(_pctl(values, 0.9), 3) if values else None,
                "sample_count": len(values),
            })
        output[kind] = series
    return output


def build_house_profile(
    history_days: dict[str, dict],
    today: date,
    *,
    ev_in_home_load: bool | None = None,
    min_days: int = MIN_COMPLETE_DAYS,
    heat_pump_in_home_load: bool = True,
) -> dict[str, Any]:
    """Calculate two separate profiles from complete recorded hours.

    profiles: household with the EV excluded, but heat pump still included.
    base_profiles: household without EV AND heat pump, for use with a separate
    temperature-dependent heat pump forecast. Never add pump or EV again to
    profiles unless the same component has first been excluded.
    """
    rows: list[tuple[date, list[float | None], list[float | None]]] = []
    skipped = 0
    inconsistent_hours = 0
    for key in sorted(history_days, reverse=True):
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        if day >= today or (today - day).days > MAX_TRAINING_DAYS:
            continue

        record = history_days[key]
        home_hours: list[float | None] = []
        base_hours: list[float | None] = []
        for hour in range(24):
            marker = f"{hour:02}:00"
            home = _valid_hour(record, "home", marker)
            if home is None:
                home_hours.append(None)
                base_hours.append(None)
                continue

            if ev_in_home_load is True:
                ev = _valid_hour(record, "ev", marker)
                if ev is None or ev > home + 0.2:
                    if ev is not None:
                        inconsistent_hours += 1
                    home_hours.append(None)
                    base_hours.append(None)
                    continue
                home = max(0.0, home - ev)
            home_hours.append(home)

            if heat_pump_in_home_load:
                hp = _valid_hour(record, "heat_pump", marker)
                if hp is None or hp > home + 0.2:
                    if hp is not None:
                        inconsistent_hours += 1
                    base_hours.append(None)
                    continue
                base_hours.append(max(0.0, home - hp))
            else:
                base_hours.append(home)

        if sum(value is not None for value in home_hours) < 22:
            skipped += 1
            continue
        rows.append((day, home_hours, base_hours))
    rows = rows[:MAX_TRAINING_DAYS]

    complete = len(rows)
    ready = complete >= min_days and ev_in_home_load is not None
    base_complete = sum(sum(x is not None for x in row[2]) >= 22 for row in rows)
    return {
        "state": ("gotowy" if ready else "ucze_sie" if ev_in_home_load is not None
                  else "niepotwierdzona_topologia_ev"),
        "complete_days": complete,
        "baseline_complete_days": base_complete,
        "baseline_ready": ready and base_complete >= min_days,
        "required_days": min_days,
        "skipped_days": skipped,
        "inconsistent_hours": inconsistent_hours,
        "ev_in_home_load": ev_in_home_load,
        "ev_excluded": ev_in_home_load is not None,
        "heat_pump_in_home_load": heat_pump_in_home_load,
        "profiles": _profile(rows, 1),
        "base_profiles": _profile(rows, 2),
        "note": (
            "Deye Load obejmuje dom, auto i pompę. Model bez EV zawiera pompę; "
            "model bazowy nie zawiera EV ani pompy. Niepełne i sprzeczne "
            "odczyty są pomijane, a nie traktowane jako zerowe."
        ),
    }
