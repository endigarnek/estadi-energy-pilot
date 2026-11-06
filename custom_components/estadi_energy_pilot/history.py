"""Bounded, persisted hourly forecast-vs-actual history; no HA imports.

Forecast is locked the previous evening, never overwritten after the fact.
Actual production is estimated from PV power samples; gaps are not invented.
All energy values are kWh and powers are W unless explicitly indicated.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from .engine import PvSlot

CHANNELS = ("pv", "home", "heat_pump", "ev")
TEMP_MIN = -45.0
TEMP_MAX = 55.0


def _temperature(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if isfinite(number) and TEMP_MIN <= number <= TEMP_MAX else None
MAX_DAYS = 45
MAX_INTERVAL_SECONDS = 30 * 60


def _power(value: Any) -> float | None:
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if isfinite(value) and 0 <= value <= 100000 else None


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _round(value: float) -> float:
    return round(value, 3)


class HistoryBook:
    """JSON-serializable, bounded local history for current HA installation."""

    def __init__(self, data: Any = None):
        self.days = dict(data.get("days", {})) if isinstance(data, dict) and isinstance(data.get("days"), dict) else {}
        self.last = data.get("last") if isinstance(data, dict) and isinstance(data.get("last"), dict) else None

    def export(self) -> dict:
        return {"version": 1, "days": self.days, "last": self.last}

    def _day(self, day_key: str) -> dict:
        return self.days.setdefault(day_key, {"actual": {}, "coverage": {}})

    def _prune(self):
        for key in sorted(self.days)[:-MAX_DAYS]:
            del self.days[key]

    def lock_forecast(self, now: datetime, pv_slots: list[PvSlot], source: str = "Solcast") -> bool:
        """Snapshot tomorrow's 24h PV projection at/after 21:00 local time.

        Do not create a daily comparison from a partial forecast.
        """
        if not (21 <= now.hour <= 23):
            return False
        tomorrow = (now + timedelta(days=1)).date()
        key = tomorrow.isoformat()
        if "forecast" in self.days.get(key, {}):
            return False
        slots = [s for s in pv_slots if s.start.astimezone(now.tzinfo).date() == tomorrow]
        coverage_hours = sum(s.duration_minutes / 60 for s in slots)
        if coverage_hours < 22:
            return False
        hourly: dict[str, float] = {}
        for slot in slots:
            dt = slot.start.astimezone(now.tzinfo)
            remaining = timedelta(minutes=slot.duration_minutes)
            while remaining.total_seconds() > 0:
                hour_end = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                part = min(hour_end - dt, remaining)
                if part.total_seconds() <= 0:
                    break
                hour_key = dt.strftime("%H:00")
                hourly[hour_key] = hourly.get(hour_key, 0.0) + slot.power_kw * (part.total_seconds() / 3600)
                remaining -= part
                dt += part
        record = self._day(key)
        record["forecast"] = {
            "locked_at": now.isoformat(),
            "source": source,
            "hours_kwh": {k: _round(v) for k, v in sorted(hourly.items())},
            "total_kwh": _round(sum(hourly.values())),
        }
        self._prune()
        return True

    def sample(self, now: datetime, *, pv: Any = None, home: Any = None,
               heat_pump: Any = None, ev: Any = None,
               outdoor_temp: Any = None) -> bool:
        """Integrate up to 30-minute gaps using trapezoids, per channel.

        Longer gaps, missing/unavailable readings and implausible spikes are
        skipped. Coverage is stored separately so incomplete days are labeled.
        """
        values = {channel: _power(value) for channel, value in
                  {"pv": pv, "home": home, "heat_pump": heat_pump, "ev": ev}.items()}
        temperature = _temperature(outdoor_temp)
        old = self.last
        self.last = {"at": now.isoformat(), "power_w": values, "outdoor_temp_c": temperature}
        if old is None:
            return False
        start = _parse_time(old.get("at"))
        previous = old.get("power_w")
        if start is None or not isinstance(previous, dict) or start.tzinfo is None:
            return False
        duration = (now.timestamp() - start.timestamp())
        if not (0 < duration <= MAX_INTERVAL_SECONDS):
            return False
        previous_temp = _temperature(old.get("outdoor_temp_c"))
        for channel in CHANNELS:
            old_power, new_power = _power(previous.get(channel)), values[channel]
            if old_power is None or new_power is None:
                continue
            cursor = start.astimezone(now.tzinfo)
            end = now
            while cursor < end:
                next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                boundary = min(end, next_hour)
                if boundary <= cursor:
                    break
                fraction1 = (cursor.timestamp() - start.timestamp()) / duration
                fraction2 = (boundary.timestamp() - start.timestamp()) / duration
                power1 = old_power + (new_power - old_power) * fraction1
                power2 = old_power + (new_power - old_power) * fraction2
                hours = (boundary.timestamp() - cursor.timestamp()) / 3600
                key = cursor.date().isoformat()
                hour = cursor.strftime("%H:00")
                record = self._day(key)
                row = record.setdefault("actual", {}).setdefault(channel, {})
                coverage = record.setdefault("coverage", {}).setdefault(channel, {})
                row[hour] = _round(row.get(hour, 0.0) + (power1 + power2) / 2 * hours / 1000)
                coverage[hour] = _round(coverage.get(hour, 0.0) + hours)
                cursor = boundary
        # Pair outdoor temperature to the same wall-clock hour as recorded
        # heat-pump consumption. Interpolate only across a <=30 min gap
        # between two valid sensor readings; never infer from missing states.
        if (previous_temp is not None and temperature is not None and
                _power(previous.get("heat_pump")) is not None and
                values["heat_pump"] is not None):
            cursor = start.astimezone(now.tzinfo)
            while cursor < now:
                boundary = min(now, cursor.replace(
                    minute=0, second=0, microsecond=0) + timedelta(hours=1))
                if boundary <= cursor:
                    break
                start_fraction = (cursor.timestamp() - start.timestamp()) / duration
                end_fraction = (boundary.timestamp() - start.timestamp()) / duration
                interpolated = (
                    previous_temp + (temperature - previous_temp) * start_fraction,
                    previous_temp + (temperature - previous_temp) * end_fraction,
                )
                hours = (boundary.timestamp() - cursor.timestamp()) / 3600
                key, hour = cursor.date().isoformat(), cursor.strftime("%H:00")
                record = self._day(key)
                degree_hours = record.setdefault("temperature_degree_hours", {})
                temp_coverage = record.setdefault("temperature_coverage", {})
                degree_hours[hour] = _round(
                    degree_hours.get(hour, 0.0) +
                    sum(interpolated) / 2 * hours
                )
                temp_coverage[hour] = _round(temp_coverage.get(hour, 0.0) + hours)
                cursor = boundary
        self._prune()
        return True

    def summary(self, day: str, *, today: str) -> dict:
        record = self.days.get(day, {})
        forecast = record.get("forecast", {})
        actual = record.get("actual", {})
        coverage = record.get("coverage", {})
        result = {"date": day, "snapshot_at": forecast.get("locked_at"),
                  "forecast_pv_kwh": forecast.get("total_kwh")}
        temperature_coverage = record.get("temperature_coverage", {})
        result["temperature_coverage_pct"] = round(
            min(100, 100 * sum(temperature_coverage.values()) / 24)
        )
        for channel in CHANNELS:
            if channel not in actual:
                result[f"{channel}_kwh"] = None
                result[f"{channel}_coverage_pct"] = 0
                continue
            result[f"{channel}_kwh"] = _round(sum(actual[channel].values()))
            result[f"{channel}_coverage_pct"] = round(min(100, 100 * sum(coverage.get(channel, {}).values()) / 24))
        sufficient = day < today and result["pv_coverage_pct"] >= 90
        result["pv_error_kwh"] = None
        result["pv_error_pct"] = None
        if sufficient and forecast.get("total_kwh") is not None:
            difference = result["pv_kwh"] - forecast["total_kwh"]
            result["pv_error_kwh"] = _round(difference)
            if forecast["total_kwh"] >= 0.5:
                result["pv_error_pct"] = round(100 * difference / forecast["total_kwh"], 1)
        result["comparable"] = bool(sufficient and forecast.get("total_kwh") is not None)
        return result

    def summaries(self, today: str, limit: int = 14) -> list[dict]:
        return [self.summary(day, today=today) for day in sorted(self.days, reverse=True)[:limit]]

    def hourly_comparison(self, day: str) -> list[dict]:
        record = self.days.get(day, {})
        forecast = record.get("forecast", {}).get("hours_kwh", {})
        actual = record.get("actual", {}).get("pv", {})
        coverage = record.get("coverage", {}).get("pv", {})
        return [{"hour": f"{hour:02}:00",
                 "forecast_kwh": forecast.get(f"{hour:02}:00"),
                 "actual_kwh": actual.get(f"{hour:02}:00"),
                 "coverage_pct": round(min(100, coverage.get(f"{hour:02}:00", 0) * 100))}
                for hour in range(24)]
