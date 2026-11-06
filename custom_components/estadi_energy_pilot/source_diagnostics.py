"""Read-only source diagnostics, with explicit reasons and no guessed values."""
from __future__ import annotations

from math import isfinite
from typing import Any


def read_numeric(state: Any, expected_unit: str, lower: float, upper: float) -> tuple[float | None, str]:
    """Validate a state, report whether missing, unavailable, nonnumeric, or out-of-range."""
    if state is None:
        return None, "nie znaleziono encji"
    raw = str(getattr(state, "state", "unknown"))
    if raw in ("unknown", "unavailable", "none", ""):
        return None, f"stan: {raw}"
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return None, "wartość nie jest liczbą"
    if not isfinite(value):
        return None, "wartość nie jest skończona"
    unit = (getattr(state, "attributes", None) or {}).get("unit_of_measurement")
    if unit != expected_unit:
        return None, f"niepoprawna jednostka: {unit or 'brak'} (oczekiwano {expected_unit})"
    if not lower <= value <= upper:
        return None, f"wartość poza zakresem {lower:g}–{upper:g}"
    return value, "OK"


def select_nonempty_sources(detected: dict, stored: dict) -> dict:
    """Restore autodetected sources if an earlier UI stored empty optional values."""
    combined = dict(detected)
    for key, value in stored.items():
        if value is not None and value != "":
            combined[key] = value
        elif key not in combined:
            combined[key] = value
    return combined
