"""Read-only power-input diagnostics for a three-phase grid guard.

Read current HA entity states on demand. A sample that is unavailable, malformed,
the wrong unit, or too old must NOT be trusted for live power decisions.
The guard never controls Deye: source freshness does not prove hardware safety.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Callable

from .const import (
    CONF_GRID_POWER, CONF_BATTERY_POWER, CONF_GRID_IMPORT_SIGN,
    CONF_BATTERY_CHARGE_SIGN, CONF_GRID_LIMIT, CONF_GRID_BUFFER,
    CONF_CHARGE_LIMIT, CONF_PHASE_CURRENT_L1, CONF_PHASE_CURRENT_L2,
    CONF_PHASE_CURRENT_L3, CONF_PHASE_VOLTAGE_L1, CONF_PHASE_VOLTAGE_L2,
    CONF_PHASE_VOLTAGE_L3, CONF_PHASE_LIMIT_L1, CONF_PHASE_LIMIT_L2,
    CONF_PHASE_LIMIT_L3,
)
from .grid_guard import calculate_grid_guard

MAX_SAMPLE_AGE_S = 120
PHASE_CURRENT_KEYS = (CONF_PHASE_CURRENT_L1, CONF_PHASE_CURRENT_L2, CONF_PHASE_CURRENT_L3)
PHASE_VOLTAGE_KEYS = (CONF_PHASE_VOLTAGE_L1, CONF_PHASE_VOLTAGE_L2, CONF_PHASE_VOLTAGE_L3)
PHASE_LIMIT_KEYS = (CONF_PHASE_LIMIT_L1, CONF_PHASE_LIMIT_L2, CONF_PHASE_LIMIT_L3)
WATCH_KEYS = (
    CONF_GRID_POWER, CONF_BATTERY_POWER,
    *PHASE_CURRENT_KEYS, *PHASE_VOLTAGE_KEYS,
)


def _number(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def read_source(get_state: Callable, entity_id: str | None,
                now: datetime, kind: str) -> dict:
    """Read one sensor: no missing/old value may silently become zero."""
    result = {"entity_id": entity_id, "value": None, "age_s": None, "status": "brak_encji"}
    if not entity_id:
        return result
    state = get_state(entity_id)
    if state is None:
        return result
    raw_state = str(getattr(state, "state", "unknown"))
    if raw_state in ("unknown", "unavailable", "none", ""):
        result["status"] = "niedostepny"
        return result
    stamp = getattr(state, "last_reported", None) or getattr(state, "last_updated", None)
    if not isinstance(stamp, datetime) or stamp.tzinfo is None:
        result["status"] = "brak_znacznika_czasu"
        return result
    age = max(0.0, (now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds())
    result["age_s"] = int(age)
    if age > MAX_SAMPLE_AGE_S:
        result["status"] = "dane_nieaktualne"
        return result
    unit = (getattr(state, "attributes", None) or {}).get("unit_of_measurement")
    units = {
        "power": {"W": 1., "kW": 1000.},
        "current": {"A": 1.},
        "voltage": {"V": 1.},
    }
    if unit not in units[kind]:
        result["status"] = "bledna_jednostka"
        return result
    value = _number(raw_state)
    if value is None:
        result["status"] = "bledna_liczba"
        return result
    value *= units[kind][unit]
    if (kind == "power" and abs(value) > 100_000 or
        kind == "current" and not 0 <= value <= 200 or
        kind == "voltage" and not 100 <= value <= 300):
        result["status"] = "poza_zakresem"
        return result
    result["value"] = value
    result["status"] = "ok"
    return result


def build_grid_readout(get_state: Callable, selected: dict,
                       now: datetime) -> dict:
    """Compute validated, read-only power advisory and full source checklist."""
    keys = (CONF_GRID_POWER, CONF_BATTERY_POWER)
    measurements = {
        key: read_source(get_state, selected.get(key), now, "power")
        for key in keys
    }
    for key in PHASE_CURRENT_KEYS:
        measurements[key] = read_source(get_state, selected.get(key), now, "current")
    for key in PHASE_VOLTAGE_KEYS:
        measurements[key] = read_source(get_state, selected.get(key), now, "voltage")

    grid_w = measurements[CONF_GRID_POWER]["value"]
    battery_w = measurements[CONF_BATTERY_POWER]["value"]
    battery_sign = int(selected.get(CONF_BATTERY_CHARGE_SIGN, 0))
    charging_w = max(0., battery_sign * battery_w) if (
        battery_w is not None and battery_sign in (-1, 1)
    ) else None

    current_vals = [measurements[k]["value"] for k in PHASE_CURRENT_KEYS]
    voltage_vals = [measurements[k]["value"] for k in PHASE_VOLTAGE_KEYS]
    phase_limits = [_number(selected.get(k, 0)) for k in PHASE_LIMIT_KEYS]
    limits_set = all(x is not None and 0 < x <= 200 for x in phase_limits)
    phase_valid = limits_set and all(v is not None for v in current_vals + voltage_vals)
    guard = calculate_grid_guard(
        grid_w, charging_w,
        import_sign=int(selected.get(CONF_GRID_IMPORT_SIGN, 0)),
        connection_limit_kw=float(selected[CONF_GRID_LIMIT]),
        reserve_kw=float(selected[CONF_GRID_BUFFER]),
        battery_max_kw=float(selected[CONF_CHARGE_LIMIT]),
        phase_currents_a=tuple(current_vals) if phase_valid else None,
        phase_limits_a=tuple(phase_limits) if phase_valid else None,
        phase_voltages_v=tuple(voltage_vals) if phase_valid else None,
    )
    decision = guard.as_dict()
    decision["phase_status"] = (
        "pomiar_3_faz" if guard.phase_checked
        else "brak_limitu_pradu_faz" if not limits_set
        else "brak_aktualnych_pomiarow_faz"
    )
    decision["source_status"] = {
        key: {"encja": entry["entity_id"], "stan": entry["status"],
              "wiek_sekund": entry["age_s"]}
        for key, entry in measurements.items()
    }
    decision["charge_sign_confirmed"] = battery_sign in (-1, 1)
    decision["import_sign_confirmed"] = int(selected.get(CONF_GRID_IMPORT_SIGN, 0)) in (-1, 1)
    decision["nominal_phase_limits_a"] = list(phase_limits)
    decision["guard_last_checked"] = now.astimezone(timezone.utc).isoformat()
    # Even with current readings, HA cannot replace physical breakers,
    # BMS constraints or measured command/readback latency of Deye.
    decision["automatic_ready"] = False
    return decision
