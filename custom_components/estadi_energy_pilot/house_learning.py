"""Conservative hourly house-demand learning from the persisted Energy Pilot history.

Separate discretionary EV charging from the ordinary household baseline ONLY
when an installer confirms that the EV is included in Deye Load.
Do not interpret missing EV data as zero consumption.
"""
from __future__ import annotations

from datetime import date, datetime
from math import ceil
from statistics import median
from typing import Any

MIN_COMPLETE_DAYS = 7
MIN_COVERAGE_PER_HOUR = 0.90
MAX_TRAINING_DAYS = 30


def _pctl(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, ceil(len(ordered) * percentile) - 1))
    return ordered[idx]


def _valid_hour(day: dict, channel: str, hour: str) -> float | None:
    amount = day.get("actual", {}).get(channel, {}).get(hour)
    cover = day.get("coverage", {}).get(channel, {}).get(hour, 0)
    if not isinstance(amount, (int, float)) or not isinstance(cover, (int, float)):
        return None
    if cover < MIN_COVERAGE_PER_HOUR or amount < 0:
        return None
    return float(amount)


def build_house_profile(
    history_days: dict[str, dict],
    today: date,
    *,
    ev_in_home_load: bool | None = None,
    min_days: int = MIN_COMPLETE_DAYS,
) -> dict[str, Any]:
    """Return P50/P90 by weekday/weekend, with explicit evidence quality.

    :param ev_in_home_load:
      True = EV is definitely included in the HA home power sensor, subtract it.
      False = EV is definitely metered outside HA home power, do not subtract.
      None = unknown; never pretend that a clean EV-excluded baseline exists.
    """
    rows: list[tuple[date, list[float]]] = []
    skipped = 0
    for key in sorted(history_days, reverse=True):
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        if day >= today or (today - day).days > MAX_TRAINING_DAYS:
            continue
        record = history_days[key]
        hours = []
        for hour in range(24):
            h = f"{hour:02}:00"
            house = _valid_hour(record, "home", h)
            if house is None:
                hours.append(None)
                continue
            if ev_in_home_load is True:
                ev = _valid_hour(record, "ev", h)
                if ev is None:
                    hours.append(None)
                    continue
                house = max(0.0, house - ev)
            hours.append(house)
        if sum(value is not None for value in hours) < 22:
            skipped += 1
            continue
        rows.append((day, hours))
    rows = rows[:MAX_TRAINING_DAYS]

    complete = len(rows)
    ready = complete >= min_days and ev_in_home_load is not None
    profiles = {}
    for kind in ("weekday", "weekend"):
        subset = [hours for day, hours in rows if (day.weekday() >= 5) == (kind == "weekend")]
        profile = []
        for hour in range(24):
            values = [d[hour] for d in subset if d[hour] is not None]
            profile.append({
                "hour": f"{hour:02}:00",
                "p50_kwh": round(median(values), 3) if values else None,
                "p90_kwh": round(_pctl(values, 0.9), 3) if values else None,
                "sample_count": len(values),
            })
        profiles[kind] = profile
    return {
        "state": "gotowy" if ready else "ucze_sie" if ev_in_home_load is not None else "niepotwierdzona_topologia_ev",
        "complete_days": complete,
        "required_days": min_days,
        "skipped_days": skipped,
        "ev_in_home_load": ev_in_home_load,
        "ev_excluded": ev_in_home_load is True or ev_in_home_load is False,
        "profiles": profiles,
        "note": (
            "Prognoza statystyczna P50/P90; skoki pralki/kuchenki są nieprzewidywalne. "
            "Dni z brakującymi pomiarami nie są udawane jako zerowe."
        ),
    }
