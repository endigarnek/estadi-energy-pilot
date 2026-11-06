"""Retrieve HA state and run the read-only optimizer every 15 minutes."""
from __future__ import annotations

import logging
import time
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
from .forecast_source import parse_forecast_solar_response
from .forecast_entry import preferred_entry
from .discovery import detect_entities
from .weather_temperature import weather_temperature_c
from .source_diagnostics import read_numeric, select_nonempty_sources
from .health import HealthJournal

_LOGGER = logging.getLogger(__name__)


class EnergyPilotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=15))
        self.entry = entry
        self._selected_settings: dict = {}
        self.storage = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.history")
        self.history = HistoryBook()
        self.health_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.health")
        self.health = HealthJournal()

    async def async_initialize(self) -> None:
        self.history = HistoryBook(await self.storage.async_load())
        self.health = HealthJournal(await self.health_store.async_load())

    def _power_w(self, key: str) -> float | None:
        """Only measure energy when the power sensor explicitly reports W/kW."""
        entity_id = self._selected_settings.get(key)
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
        entity_id = self._selected_settings.get(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if isfinite(value) and -1000000 < value < 1000000 else None

    def diagnostics(self):
        return self.health.view(dt_util.utcnow())

    async def _async_update_data(self):
        started = time.monotonic()
        self.health.attempt(dt_util.utcnow())
        try:
            data = await self._async_collect_data()
            if not data.get("available"):
                status, reason = "warning", data.get("reason", "Brak pełnych danych")
            elif not data.get("night").can_calculate or not data.get("afternoon").can_calculate:
                status, reason = "warning", data.get("forecast_error") or "Niepełna prognoza PV — brak pełnego planu"
            else:
                status, reason = "ok", "Wszystkie wymagane odczyty i cele SOC dostępne"
        except Exception as err:
            _LOGGER.exception("ESTADI Energy Pilot refresh failed")
            status, reason = "error", f"Błąd odświeżenia: {type(err).__name__}"
            data = {"available": False, "reason": reason}
        self.health.finish(
            dt_util.utcnow(), status, reason,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        self.health_store.async_delay_save(self.health.export, 60)
        data["health"] = self.diagnostics()
        return data

    async def _async_collect_data(self):
        selected = {**DEFAULTS, **select_nonempty_sources(
            detect_entities(self.hass.states.async_all()),
            {**self.entry.data, **self.entry.options},
        )}
        self._selected_settings = selected
        now = dt_util.now()
        attrs = []
        for key in (CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW, CONF_SOLCAST_DAY3):
            entity_id = selected.get(key)
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is not None:
                attrs.append(dict(state.attributes))
        pv_slots = parse_pv_slots(*attrs)
        forecast_source = "Solcast" if pv_slots else "Brak prognozy"
        forecast_error = None

        # Prefer the user's existing Forecast.Solar integration. Its service
        # returns cached hourly data; no API key and no additional provider.
        forecast_entry_id = preferred_entry(
            self.hass, stored=selected.get(CONF_FORECAST_SOLAR_ENTRY)
        )
        if forecast_entry_id:
            if self.hass.services.has_service("forecast_solar", "get_forecast"):
                try:
                    response = await self.hass.services.async_call(
                        "forecast_solar", "get_forecast",
                        {"config_entry": forecast_entry_id, "resolution": "hourly"},
                        blocking=True, return_response=True,
                    )
                    forecast_slots = parse_forecast_solar_response(response)
                    if forecast_slots:
                        pv_slots = forecast_slots
                        forecast_source = "Forecast.Solar"
                    else:
                        forecast_error = "Forecast.Solar nie zwrócił danych godzinowych"
                except Exception as err:
                    _LOGGER.warning("Forecast.Solar hourly forecast unavailable: %s", err)
                    forecast_error = "Nie udało się pobrać prognozy Forecast.Solar"
            else:
                forecast_error = "Zaktualizuj Home Assistant: brak akcji Forecast.Solar get_forecast"

        self.history.lock_forecast(now, pv_slots, source=forecast_source)
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
            "forecast_source": forecast_source,
            "forecast_error": forecast_error,
            "history_last_hour": last_hour_comparison,
            "history_last_hour_at": last_hour.replace(minute=0, second=0, microsecond=0).isoformat(),
            "history_today": self.history.summary(date_today, today=date_today),
            "history_yesterday": self.history.summary(date_yesterday, today=date_today),
            "history_recent": self.history.summaries(date_today),
            "history_hours": self.history.hourly_comparison(date_yesterday),
        }
        soc_entity = selected.get(CONF_BATTERY_SOC)
        soc, soc_reason = read_numeric(
            self.hass.states.get(soc_entity) if soc_entity else None, "%", 0, 100
        )
        temp_entity = selected.get(CONF_OUTDOOR_TEMP)
        outdoor_temp, temp_reason = read_numeric(
            self.hass.states.get(temp_entity) if temp_entity else None, "°C", -70, 65
        )
        temperature_source = "sensor" if outdoor_temp is not None else "weather"
        weather_entity = selected.get(CONF_WEATHER)
        weather_reason = "nie przypisano encji pogodowej"
        if outdoor_temp is None and weather_entity:
            outdoor_temp = weather_temperature_c(self.hass.states.get(weather_entity))
            weather_reason = "OK" if outdoor_temp is not None else "brak poprawnej temperatury z pogody"

        diagnostics = {
            "soc_encja": soc_entity,
            "soc_status": soc_reason,
            "soc_wartosc": soc,
            "temperatura_encja": temp_entity,
            "temperatura_status": temp_reason,
            "pogoda_encja": weather_entity,
            "pogoda_status": weather_reason,
            "temperatura_wartosc": outdoor_temp,
            "zrodlo_temperatury": temperature_source if outdoor_temp is not None else None,
            "prognoza_zrodlo": forecast_source,
            "prognoza_blad": forecast_error,
        }
        history["diagnostics"] = diagnostics
        if soc is None or outdoor_temp is None:
            missing = []
            if soc is None:
                missing.append(f"SOC ({soc_reason})")
            if outdoor_temp is None:
                missing.append("temperatura (czujnik: " + temp_reason
                               + "; pogoda: " + weather_reason + ")")
            return {**history, "available": False,
                    "reason": "Brak danych: " + ", ".join(missing)}

        temperatures = []
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
                now=now, pv_attrs=attrs, pv_slots=pv_slots, temps=temperatures,
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
        plan["temperature_source"] = "hourly" if temperatures else temperature_source
        plan["current_soc"] = round(soc, 1)
        return plan
