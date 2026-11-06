"""Retrieve HA state and run the read-only optimizer every 15 minutes."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import *  # noqa: F403
from .engine import get_all_plans, parse_weather_slots

_LOGGER = logging.getLogger(__name__)


class EnergyPilotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=15))
        self.entry = entry

    def _entity_value(self, key: str) -> float | None:
        entity_id = self.entry.data.get(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if -1000000 < value < 1000000 else None

    async def _async_update_data(self):
        selected = {**DEFAULTS, **self.entry.data, **self.entry.options}
        now = dt_util.now()
        soc = self._entity_value(CONF_BATTERY_SOC)
        outdoor_temp = self._entity_value(CONF_OUTDOOR_TEMP)
        if soc is None or outdoor_temp is None or not 0 <= soc <= 100:
            return {"available": False, "reason": "Brak prawidłowego SOC lub temperatury zewnętrznej"}
        attrs = []
        for key in (CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW, CONF_SOLCAST_DAY3):
            entity_id = selected.get(key)
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is not None:
                attrs.append(dict(state.attributes))
        temperatures = []
        weather_entity = selected.get(CONF_WEATHER)
        if weather_entity:
            try:
                response = await self.hass.services.async_call(
                    "weather", "get_forecasts", {"type": "hourly", "entity_id": weather_entity},
                    blocking=True, return_response=True)
                hourly = response.get(weather_entity, {}).get("forecast", []) if response else []
                temperatures = parse_weather_slots(hourly)
            except Exception as err:  # weather optional, safe fallback to current temperature
                _LOGGER.warning("Hourly weather unavailable: %s", err)

        try:
            plan = get_all_plans(
                now=now, pv_attrs=attrs, temps=temperatures,
                current_temp=outdoor_temp, soc=soc,
                capacity_kwh=float(selected[CONF_CAPACITY]),
                baseload_w=float(selected[CONF_BASE_W]),
                reserve_soc=int(selected[CONF_RESERVE]),
                max_soc=int(selected[CONF_MAX_SOC]),
                pv_discount_pct=int(selected[CONF_PV_DISCOUNT]),
                efficiency_pct=int(selected[CONF_EFFICIENCY]),
                margin_kwh=float(selected[CONF_MARGIN]),
                mild_w=float(selected[CONF_MILD_W]),
                cold_w=float(selected[CONF_COLD_W]),
                night_start=int(selected[CONF_NIGHT_START]),
                night_end=int(selected[CONF_NIGHT_END]),
                midday_start=int(selected[CONF_MIDDAY_START]),
                afternoon_end=int(selected[CONF_AFTERNOON_END]),
            )
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as err:
            _LOGGER.error("Cannot calculate energy plan: %s", err)
            return {"available": False, "reason": "Błędne ustawienia — sprawdź konfigurację"}
        plan["available"] = True
        plan["temperature_source"] = "hourly" if temperatures else "current"
        plan["current_soc"] = round(soc, 1)
        return plan
