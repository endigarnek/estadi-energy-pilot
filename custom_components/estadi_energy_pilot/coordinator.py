"""Retrieve HA state and run the read-only optimizer every 15 minutes."""
from __future__ import annotations

import logging
from datetime import timedelta
from math import isfinite

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import *  # noqa: F403
from .engine import get_all_plans, parse_pv_slots, parse_weather_slots
from .history import HistoryBook

_LOGGER = logging.getLogger(__name__)


class EnergyPilotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=15))
        self.entry = entry
        self.storage = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.history")
        self.history = HistoryBook()

    async def async_initialize(self) -> None:
        self.history = HistoryBook(await self.storage.async_load())

    def _power_w(self, key: str) -> float | None:
        """Only measure energy when the power sensor explicitly reports W/kW."""
        settings = {**self.entry.data, **self.entry.options}
        entity_id = settings.get(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if not state or state.state in ("unknown", "unavailable"):
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit not in ("W", "kW"):
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        watts = value * (1000 if unit == "kW" else 1)
        return watts if isfinite(watts) and 0 <= watts <= 100000 else None

    def _entity_value(self, key: str) -> float | None:
        entity_id = {**self.entry.data, **self.entry.options}.get(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if isfinite(value) and -1000000 < value < 1000000 else None

    async def _async_update_data(self):
        selected = {**DEFAULTS, **self.entry.data, **self.entry.options}
        now = dt_util.now()
        attrs = []
        for key in (CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW, CONF_SOLCAST_DAY3):
            entity_id = selected.get(key)
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is not None:
                attrs.append(dict(state.attributes))
        self.history.lock_forecast(now, parse_pv_slots(*attrs))
        self.history.sample(
            now,
            pv=self._power_w(CONF_PV_POWER),
            home=self._power_w(CONF_HOME_POWER),
            heat_pump=self._power_w(CONF_HEAT_PUMP_POWER),
            ev=self._power_w(CONF_EV_POWER),
        )
        self.storage.async_delay_save(self.history.export, 60)
        date_today = now.date().isoformat()
        date_yesterday = (now.date() - timedelta(days=1)).isoformat()
        last_hour = now - timedelta(hours=1)
        last_hour_key = last_hour.strftime("%H:00")
        last_hour_comparison = next(
            (point for point in self.history.hourly_comparison(last_hour.date().isoformat())
             if point["hour"] == last_hour_key), None
        )
        history = {
            "history_last_hour": last_hour_comparison,
            "history_last_hour_at": last_hour.replace(minute=0, second=0, microsecond=0).isoformat(),
            "history_today": self.history.summary(date_today, today=date_today),
            "history_yesterday": self.history.summary(date_yesterday, today=date_today),
            "history_recent": self.history.summaries(date_today),
            "history_hours": self.history.hourly_comparison(date_yesterday),
        }
        soc = self._entity_value(CONF_BATTERY_SOC)
        outdoor_temp = self._entity_value(CONF_OUTDOOR_TEMP)
        if soc is None or outdoor_temp is None or not 0 <= soc <= 100:
            return {**history, "available": False,
                    "reason": "Brak prawidłowego SOC lub temperatury zewnętrznej"}

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
            return {**history, "available": False,
                    "reason": "Błędne ustawienia — sprawdź konfigurację"}
        plan.update(history)
        plan["available"] = True
        plan["temperature_source"] = "hourly" if temperatures else "current"
        plan["current_soc"] = round(soc, 1)
        return plan
