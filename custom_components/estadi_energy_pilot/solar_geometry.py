"""Astronomical daytime coverage for PV forecasts, dependency-free and read-only.

Forecast.Solar often returns only sunlit production periods. A missing record
at 04:00 in November is NOT an incomplete forecast; missing records when the
sun is high enough to produce energy remain a hard error.

Solar position is approximate NOAA solar geometry in UTC. We treat sun below
2 degrees above the horizon as *low-light*: missing PV is bounded to zero only
in that category. This is still a model assumption, explicitly reported.
No grid/battery commands are ever issued from these functions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import acos, asin, cos, isfinite, pi, radians, sin
from typing import Iterable

from .engine import PvSlot

MIN_SOLAR_ELEVATION_DEG = 2.0
STEP = timedelta(minutes=15)


def solar_elevation(at: datetime, latitude: float, longitude: float) -> float:
    """Approximate solar elevation in degrees, independent of local DST."""
    if at.tzinfo is None:
        raise ValueError("Odczyt czasu nie ma strefy UTC")
    if not all(isfinite(float(v)) for v in (latitude, longitude)):
        raise ValueError("Niepoprawne współrzędne instalacji")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Niepoprawny zakres współrzędnych instalacji")
    utc = at.astimezone(timezone.utc)
    fraction_hour = (utc.hour + utc.minute / 60 +
                     utc.second / 3600 + utc.microsecond / 3_600_000_000)
    days = 366 if (utc.year % 4 == 0 and
                      (utc.year % 100 != 0 or utc.year % 400 == 0)) else 365
    gamma = 2 * pi / days * (utc.timetuple().tm_yday - 1 +
                             (fraction_hour - 12) / 24)
    equation = 229.18 * (
        0.000075 + 0.001868 * cos(gamma) - 0.032077 * sin(gamma)
        - 0.014615 * cos(2 * gamma) - 0.040849 * sin(2 * gamma)
    )
    declination = (
        0.006918 - 0.399912 * cos(gamma) + 0.070257 * sin(gamma)
        - 0.006758 * cos(2 * gamma) + 0.000907 * sin(2 * gamma)
        - 0.002697 * cos(3 * gamma) + 0.00148 * sin(3 * gamma)
    )
    solar_minutes = (fraction_hour * 60 + equation + 4 * longitude) % 1440
    hour_angle = radians(solar_minutes / 4 - 180)
    cos_zenith = (sin(radians(latitude)) * sin(declination) +
                  cos(radians(latitude)) * cos(declination) * cos(hour_angle))
    return 90 - acos(max(-1.0, min(1.0, cos_zenith))) * 180 / pi


def required_forecast(at: datetime, *, latitude: float | None = None,
                      longitude: float | None = None,
                      legacy_hours: tuple[int, int] = (4, 22)) -> bool:
    """Whether PV data are mandatory for this quarter-hour.

    Use real approximate solar elevation when geographic site data exist.
    Test both ends to avoid skipping a step entering daylight. Without a site
    use the legacy conservative (broader) hourly bound; never guess location.
    """
    if latitude is None or longitude is None:
        hour = at.hour + at.minute / 60
        return legacy_hours[0] <= hour < legacy_hours[1]
    return max(
        solar_elevation(at, latitude, longitude),
        solar_elevation(at + STEP, latitude, longitude),
    ) > MIN_SOLAR_ELEVATION_DEG


def slot_coverage(start: datetime, end: datetime,
                  pv_slots: Iterable[PvSlot]) -> float:
    """Fraction of interval supported by actual hourly/half-hourly PV slots."""
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    secs = 0.0
    for slot in pv_slots:
        if slot.start.tzinfo is None or not isfinite(slot.power_kw) or slot.power_kw < 0:
            continue
        until = slot.start.astimezone(timezone.utc) + timedelta(minutes=slot.duration_minutes)
        since = slot.start.astimezone(timezone.utc)
        secs += max(0.0, (min(end_utc, until) - max(start_utc, since)).total_seconds())
    total = (end_utc - start_utc).total_seconds()
    return min(1.0, secs / total) if total > 0 else 0.0


def summarize_forecast(now: datetime, pv_slots: list[PvSlot], *,
                       latitude: float | None, longitude: float | None,
                       horizon_hours: int = 48) -> dict:
    """Explain covered/missing daylight and explicitly inferred low-light."""
    at = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    required = available = lowlight_assumed = 0
    missing_at = None
    for _ in range(horizon_hours * 4):
        coverage = slot_coverage(at, at + STEP, pv_slots)
        is_required = required_forecast(
            at, latitude=latitude, longitude=longitude
        ) if latitude is not None and longitude is not None else True
        if is_required:
            required += 1
            if coverage >= .999:
                available += 1
            elif missing_at is None:
                missing_at = at.isoformat()
        elif coverage < .999:
            lowlight_assumed += 1
        at += STEP
    end = max((s.start + timedelta(minutes=s.duration_minutes) for s in pv_slots),
              default=None)
    return {
        "available_daylight_steps": available,
        "required_daylight_steps": required,
        "missing_daylight_steps": required - available,
        "first_missing_daylight_at": missing_at,
        "covered_daylight_pct": round(100 * available / required, 1) if required else 0.0,
        "lowlight_assumed_zero_steps": lowlight_assumed,
        "first_forecast_at": min((s.start for s in pv_slots), default=None).isoformat()
            if pv_slots else None,
        "last_forecast_end_at": end.isoformat() if end else None,
        "time_steps": len(pv_slots),
        "solar_elevation_threshold_deg": MIN_SOLAR_ELEVATION_DEG,
        "location_confirmed": latitude is not None and longitude is not None,
    }
