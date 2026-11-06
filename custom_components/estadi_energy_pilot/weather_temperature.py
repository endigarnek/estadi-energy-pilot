"""Read outdoor temperature from a Home Assistant weather entity safely."""
from __future__ import annotations
from math import isfinite
from typing import Any


def weather_temperature_c(state: Any) -> float | None:
    if state is None or getattr(state, "state", None) in ("unknown", "unavailable"):
        return None
    attributes = getattr(state, "attributes", {}) or {}
    try:
        value = float(attributes.get("temperature"))
    except (TypeError, ValueError):
        return None
    if not isfinite(value):
        return None
    unit = attributes.get("temperature_unit", "°C")
    if unit == "°F":
        value = (value - 32) * 5 / 9
    elif unit not in ("°C", "C"):
        return None
    return value if -70 <= value <= 65 else None
