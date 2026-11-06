"""Read-only inventory of six Deye TOU slots visible in Home Assistant.

Entity names depend on firmware / Modbus integration. This inspector uses
strict, explicit naming patterns, reports ambiguous and missing fields, and
NEVER guesses register mappings or sends a Home Assistant service call.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable

SLOT_COUNT = 6
SLOT_FIELDS = ("time", "soc", "power", "charging")
FIELDS = {
    "time": {"time", "start", "start_time"},
    "soc": {"soc", "target_soc", "battery_soc"},
    "power": {"power", "charge_power", "charging_power", "max_charge_power"},
    "charging": {"charging", "grid_charging", "grid_charge", "charge_mode", "charge_enable"},
}
# Only sensor/read-back entities; number/select/time/switch are read without writing.
SLOT_RE = re.compile(
    r"^(sensor|number|select|time|switch)\.deye_"
    r"(?:(?:program|time_of_use|tou)_(?P<slot_a>[1-6])_(?P<field_a>[a-z0-9_]+)"
    r"|time_of_use_program_(?P<slot_b>[1-6])_(?P<field_b>[a-z0-9_]+))$"
)
GLOBALS = (
    "select.deye_time_of_use", "switch.deye_time_of_use",
    "switch.deye_grid_charging", "select.deye_work_mode",
    "sensor.deye_inverter_model", "sensor.deye_model",
)


def _read_value(state: Any, field: str) -> tuple[Any, str]:
    """Validate state type, retain its measurement unit; no implicit power unit."""
    raw = str(getattr(state, "state", "unknown"))
    if raw.strip().lower() in ("unknown", "unavailable", "none", ""):
        return None, "niedostepny"
    domain = getattr(state, "entity_id", "").split(".", 1)[0]
    unit = (getattr(state, "attributes", None) or {}).get("unit_of_measurement")
    if field == "time":
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", raw):
            return None, "bledny_czas"
        return raw[:5], "ok"
    if field == "soc":
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None, "nieprawidlowy_soc"
        if not isfinite(value) or not 0 <= value <= 100:
            return None, "nieprawidlowy_soc"
        if unit not in (None, "%"):
            return None, "bledna_jednostka_soc"
        return round(value, 1), "ok"
    if field == "power":
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None, "nieprawidlowa_moc"
        if not isfinite(value) or value < 0 or value > 100000:
            return None, "nieprawidlowa_moc"
        # Some Deye integrations expose power as a percentage of a
        # register's maximum, not in kW. Never silently reinterpret it.
        if unit not in ("W", "kW", "%"):
            return None, "niepotwierdzona_jednostka_mocy"
        if unit == "%":
            return (f"{value:g} %", "ok") if value <= 100 else (None, "nieprawidlowa_moc")
        kw = value / 1000 if unit == "W" else value
        if kw > 100:
            return None, "nieprawidlowa_moc"
        return f"{kw:.3f} kW", "ok"
    # Charging is a device-specific mode. Show the source state verbatim,
    # but DO NOT assume its semantic meaning (e.g. 'Grid' vs 'Gen').
    if domain in ("select", "switch", "sensor"):
        return raw[:100], "ok"
    return None, "nieznany_typ_sterowania"


def _field_from_match(match: re.Match) -> tuple[int, str] | None:
    slot = int(match.group("slot_a") or match.group("slot_b"))
    suffix = match.group("field_a") or match.group("field_b")
    for field, candidates in FIELDS.items():
        if suffix in candidates:
            return slot, field
    return None


def inspect_tou(states: Iterable[Any], now: datetime) -> dict:
    """Enumerate TOU slots, global switches and blockers without writing data."""
    if now.tzinfo is None:
        raise ValueError("Inspection timestamp must include UTC offset")
    index = {getattr(state, "entity_id", ""): state for state in states}
    found: dict[tuple[int, str], list[Any]] = {}
    for entity_id, state in index.items():
        match = SLOT_RE.fullmatch(entity_id)
        if match is None:
            continue
        decoded = _field_from_match(match)
        if decoded is not None:
            found.setdefault(decoded, []).append(state)

    slots = []
    missing_count = 0
    ambiguous_count = 0
    present_count = 0
    for slot in range(1, SLOT_COUNT + 1):
        row: dict[str, Any] = {"slot": slot}
        for field in SLOT_FIELDS:
            matches = found.get((slot, field), [])
            if not matches:
                missing_count += 1
                row[field] = {"encja": None, "wartosc": None, "status": "brak"}
                continue
            if len(matches) != 1:
                ambiguous_count += 1
                row[field] = {
                    "encja": [match.entity_id for match in matches],
                    "wartosc": None, "status": "niejednoznaczne",
                }
                continue
            state = matches[0]
            value, status = _read_value(state, field)
            if status == "ok":
                present_count += 1
            row[field] = {
                "encja": state.entity_id, "wartosc": value, "status": status,
            }
        slots.append(row)

    globals_found = {}
    for entity_id in GLOBALS:
        state = index.get(entity_id)
        if state is not None:
            raw = str(getattr(state, "state", "unknown"))
            globals_found[entity_id] = None if raw in ("unknown", "unavailable") else raw[:100]

    # Show near-match entity IDs, so the user does not have to hunt through
    # HA developer tools when their Modbus integration has different names.
    identified_ids = {
        state.entity_id for candidates in found.values() for state in candidates
    }
    possible_unmapped = sorted([
        entity_id for entity_id in index
        if re.match(r"^(sensor|number|select|time|switch)\.", entity_id)
        and any(marker in entity_id for marker in ("deye", "time_of_use", "tou"))
        and any(marker in entity_id for marker in ("program", "time_of_use", "tou"))
        and entity_id not in identified_ids and entity_id not in GLOBALS
    ])[:30]

    complete = present_count == SLOT_COUNT * len(SLOT_FIELDS)
    if not found:
        status = "nie_wykryto"
        reason = "Brak encji Deye TOU według znanych nazw; integracja może stosować inne identyfikatory"
    elif complete:
        status = "odczytano_6_programow"
        reason = "Odczytano 6 programów; znaczenie i możliwość zapisu wymagają testów na falowniku"
    else:
        status = "niekompletne"
        reason = "Część pól harmonogramu Deye jest niedostępna lub niejednoznaczna"

    blockers = []
    if not complete:
        blockers.append(f"Brak poprawnego odczytu {SLOT_COUNT * len(SLOT_FIELDS) - present_count} z 24 pól TOU")
    if ambiguous_count:
        blockers.append(f"Niejednoznaczne przypisania pól: {ambiguous_count}")
    blockers.extend((
        "Niepotwierdzony dokładny model i wersja firmware Deye",
        "Niepotwierdzona semantyka i możliwość bezpiecznego zapisu rejestrów TOU",
        "Nieprzetestowany zapis, odczyt zwrotny i przywrócenie konfiguracji",
        "Niepotwierdzone sprzętowe limity prądów na wszystkich trzech fazach",
        "Niezweryfikowana reakcja Deye/BMS przy zmianie mocy ładowania",
    ))
    return {
        "status": status,
        "przyczyna": reason,
        "odczytane_pola": present_count,
        "lacznie_pol": SLOT_COUNT * len(SLOT_FIELDS),
        "brakujace_pola": missing_count,
        "niejednoznaczne_pola": ambiguous_count,
        "stan_globalny": globals_found,
        "inne_mozliwe_encje": possible_unmapped,
        "programy": slots,
        "blokady": blockers,
        "odczyt_o": now.astimezone(timezone.utc).isoformat(),
        "automatyzacja_gotowa": False,
        "odczyt_bez_zapisu": True,
    }


def snapshot_config(inventory: dict) -> dict | None:
    """Create read-only snapshot only when all values are present and valid."""
    if inventory.get("status") != "odczytano_6_programow":
        return None
    return {
        "captured_at": inventory["odczyt_o"],
        "global_settings": inventory["stan_globalny"],
        "slots": inventory["programy"],
    }


def changed_fields(previous: dict | None, inventory: dict) -> list[str]:
    """Compare read-back settings to first snapshot; never restore automatically."""
    if previous is None:
        return []
    original = previous.get("slots") or []
    current = inventory.get("programy") or []
    changes = []
    for i in range(min(len(original), len(current), SLOT_COUNT)):
        for field in SLOT_FIELDS:
            old = (original[i].get(field) or {}).get("wartosc")
            new = (current[i].get(field) or {}).get("wartosc")
            if old is not None and new is not None and old != new:
                changes.append(f"Program {i + 1}: {field}: {old} → {new}")
    for key, old in (previous.get("global_settings") or {}).items():
        new = (inventory.get("stan_globalny") or {}).get(key)
        if new is not None and old is not None and new != old:
            changes.append(f"{key}: {old} → {new}")
    return changes[:30]
