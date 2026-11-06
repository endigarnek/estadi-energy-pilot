"""Detect known and unambiguous HA entities without guessing missing devices.

Only *existing* entities are selected; saved explicit choices always take priority.
No network requests, no Home Assistant dependency and no hardware writes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Any

from .const import (
    CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW, CONF_SOLCAST_DAY3,
    CONF_BATTERY_SOC, CONF_OUTDOOR_TEMP, CONF_WEATHER,
    CONF_PV_POWER, CONF_HOME_POWER, CONF_HEAT_PUMP_POWER, CONF_EV_POWER,
)

POWER_PREFERRED = {
    CONF_PV_POWER: ("sensor.deye_pv_power",),
    CONF_HOME_POWER: ("sensor.deye_load_power",),
    CONF_HEAT_PUMP_POWER: ("sensor.shellyem3_08f9e051e0b0_channel_b_power",),
    CONF_EV_POWER: ("sensor.moc_ladowarki_poprawna",),
}

SOC_PREFERRED = (
    "sensor.deye_battery_soc",
    "sensor.deye_battery_level",
    "sensor.deye_battery_state_of_charge",
)
TEMP_PREFERRED = (
    "sensor.temperatura_zewnetrzna",
    "sensor.outdoor_temperature",
    "sensor.outside_temperature",
)


def _is_sensor(state: Any, unit: tuple[str, ...]) -> bool:
    return (
        getattr(state, "entity_id", "").startswith("sensor.")
        and state.attributes.get("unit_of_measurement") in unit
    )


def _first_existing(index: dict, ids: tuple[str, ...], unit: tuple[str, ...]) -> str | None:
    for entity_id in ids:
        state = index.get(entity_id)
        if state is not None and _is_sensor(state, unit):
            return entity_id
    return None


def _unique(matches: list[str]) -> str | None:
    return matches[0] if len(matches) == 1 else None


def detect_entities(states: Iterable[Any]) -> dict[str, str]:
    """Return safe suggestions for this installation.

    Known customer-specific IDs only win if still present, with appropriate unit.
    For unknown SOC / Solcast / outdoor temperature allow a single unambiguous
    matching candidate; otherwise leave the field empty to avoid wrong results.
    """
    index = {state.entity_id: state for state in states}
    chosen: dict[str, str] = {}

    for key, names in POWER_PREFERRED.items():
        entity = _first_existing(index, names, ("W", "kW"))
        if entity:
            chosen[key] = entity

    soc = _first_existing(index, SOC_PREFERRED, ("%",))
    if not soc:
        soc = _unique(sorted([
            entity_id for entity_id, state in index.items()
            if entity_id.startswith("sensor.deye_")
            and ("soc" in entity_id or "battery_level" in entity_id
                 or "state_of_charge" in entity_id)
            and _is_sensor(state, ("%",))
        ]))
    if soc:
        chosen[CONF_BATTERY_SOC] = soc

    temp = _first_existing(index, TEMP_PREFERRED, ("°C", "C", "°F"))
    if not temp:
        temp = _unique(sorted([
            entity_id for entity_id, state in index.items()
            if _is_sensor(state, ("°C", "C", "°F"))
            and any(tag in entity_id for tag in ("outdoor", "outside", "zewnetrz", "zewn_trz"))
        ]))
    if temp:
        chosen[CONF_OUTDOOR_TEMP] = temp

    for key, markers in (
        (CONF_SOLCAST_TODAY, ("today", "dzisiaj")),
        (CONF_SOLCAST_TOMORROW, ("tomorrow", "jutro")),
        (CONF_SOLCAST_DAY3, ("day_3", "day3", "pojutrze")),
    ):
        matches = []
        for entity_id, state in index.items():
            if not entity_id.startswith("sensor.") or "solcast" not in entity_id:
                continue
            if not any(marker in entity_id for marker in markers):
                continue
            if isinstance(state.attributes.get("detailedForecast"), list) or isinstance(
                state.attributes.get("detailedHourly"), list
            ):
                matches.append(entity_id)
        match = _unique(sorted(matches))
        if match:
            chosen[key] = match

    weather = [k for k in index if k.startswith("weather.")]
    if len(weather) == 1:
        chosen[CONF_WEATHER] = weather[0]
    return chosen
