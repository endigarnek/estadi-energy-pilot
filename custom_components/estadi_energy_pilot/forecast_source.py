"""Normalize Forecast.Solar action response to hourly PV production slots.

Forecast.Solar service returns wh_period in Wh keyed by ISO start times.
Hourly energy is authoritative, rather than assuming watts is energy.
This module has no dependency on Home Assistant and cannot modify hardware.
"""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from .engine import PvSlot


def parse_forecast_solar_response(response: Any) -> list[PvSlot]:
    """Convert forecast_solar.get_forecast(resolution='hourly') safely."""
    if not isinstance(response, dict):
        return []
    energy = response.get("wh_period")
    watts = response.get("watts")
    if not isinstance(energy, dict) and not isinstance(watts, dict):
        return []

    slots: dict[datetime, PvSlot] = {}
    source = energy if isinstance(energy, dict) and energy else watts
    for raw_start, raw in source.items():
        try:
            instant = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
            number = float(raw)
        except (ValueError, TypeError):
            continue
        if instant.tzinfo is None or not isfinite(number) or number < 0:
            continue

        # Hourly wh_period is energy in Wh over 1 hour, hence kWh == mean kW.
        # The action must have been invoked with resolution='hourly'.
        kw = number / 1000.0
        slots[instant] = PvSlot(instant, kw, 60)
    return sorted(slots.values(), key=lambda s: s.start)


def choose_forecast_entry(entry_ids: list[str], linked_sensor_entry: str | None = None,
                          stored_entry: str | None = None) -> str | None:
    """Never guess which of several Forecast.Solar entries represents this PV site."""
    if stored_entry and stored_entry in entry_ids:
        return stored_entry
    if linked_sensor_entry and linked_sensor_entry in entry_ids:
        return linked_sensor_entry
    return entry_ids[0] if len(entry_ids) == 1 else None
