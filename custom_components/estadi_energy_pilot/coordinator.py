"""Retrieve HA state and run the read-only optimizer every 15 minutes."""
from __future__ import annotations

import logging
import time
from dataclasses import replace
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
from .battery_model import BatteryModel
from .grid_guard import calculate_grid_guard
from .tariffs import tariff_zone, next_cheap_window, zone_prices, is_day_off
from .charge_planner import propose
from .house_learning import build_house_profile, resolve_ev_topology
from .simulation_48h import simulate_48h

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

    def _kw_or_none(self, key: str):
        watts = self._power_w(key)
        return round(watts / 1000, 2) if watts is not None else None

    def _signed_power_w(self, key: str):
        entity_id = self._selected_settings.get(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit not in ("W", "kW"):
            return None
        try:
            value = float(state.state) * (1000 if unit == "kW" else 1)
        except (TypeError, ValueError):
            return None
        return value if isfinite(value) and -100000 <= value <= 100000 else None

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
        model = BatteryModel(
            nominal_kwh=float(selected[CONF_NOMINAL_KWH]),
            soh_pct=float(selected[CONF_SOH]),
            minimum_soc=float(selected[CONF_MIN_SOC]),
            maximum_soc=float(selected[CONF_USER_MAX_SOC]),
            correction_pp=float(selected[CONF_CORRECTION]),
        )
        tariff = selected[CONF_TARIFF]
        tariff_band = tariff_zone(now, tariff)
        tariff_window = next_cheap_window(now, tariff)
        prices = zone_prices(
            tariff, selected[CONF_PRICE_CHEAP],
            selected[CONF_PRICE_PEAK], selected[CONF_PRICE_EVENING],
        )
        grid_w = self._signed_power_w(CONF_GRID_POWER)
        battery_w = self._signed_power_w(CONF_BATTERY_POWER)
        battery_sign = int(selected[CONF_BATTERY_CHARGE_SIGN])
        charging_w = max(0.0, battery_w * battery_sign) if (
            battery_w is not None and battery_sign in (-1, 1)
        ) else None
        guard = calculate_grid_guard(
            grid_w, charging_w,
            import_sign=int(selected[CONF_GRID_IMPORT_SIGN]),
            connection_limit_kw=float(selected[CONF_GRID_LIMIT]),
            reserve_kw=float(selected[CONF_GRID_BUFFER]),
            battery_max_kw=float(selected[CONF_CHARGE_LIMIT]),
        )
        v2_info = {
            "model": model.as_dict(),
            "grid": guard.as_dict(),
            "tariff": tariff,
            "tariff_zone": tariff_band,
            "next_cheap_start": tariff_window[0].isoformat() if tariff_window else None,
            "next_cheap_end": tariff_window[1].isoformat() if tariff_window else None,
            "price_current_pln_kwh": prices.get(tariff_band) if prices else None,
            "prices_confirmed": prices is not None,
            "automation_enabled": False,
            "charging_schedule": None,
            "live": {
                "pv_kw": self._kw_or_none(CONF_PV_POWER),
                "home_kw": self._kw_or_none(CONF_HOME_POWER),
                "heat_pump_kw": self._kw_or_none(CONF_HEAT_PUMP_POWER),
                "ev_kw": self._kw_or_none(CONF_EV_POWER),
            },
        }
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
        ev_topology = resolve_ev_topology(selected.get(CONF_EV_TOPOLOGY))
        ev_included = ev_topology == "included"
        learned = build_house_profile(
            self.history.days, now.date(),
            ev_in_home_load=ev_included,
            heat_pump_in_home_load=True,
        )
        v2_info["house_learning"] = learned
        date_today = now.date().isoformat()
        date_yesterday = (now.date() - timedelta(days=1)).isoformat()
        last_hour = now - timedelta(hours=1)
        last_hour_key = last_hour.strftime("%H:00")
        last_hour_comparison = next(
            (point for point in self.history.hourly_comparison(last_hour.date().isoformat())
             if point["hour"] == last_hour_key), None
        )
        history = {
            "energy_2_0": v2_info,
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
                capacity_kwh=model.estimated_chemical_capacity_kwh,
                baseload_w=float(selected[CONF_BASE_W]),
                reserve_soc=int(model.minimum_soc),
                max_soc=int(model.maximum_soc),
                pv_discount_pct=int(selected[CONF_PV_DISCOUNT]),
                efficiency_pct=int(selected[CONF_EFFICIENCY]),
                margin_kwh=float(selected[CONF_MARGIN]),
                mild_w=float(selected[CONF_MILD_W]),
                cold_w=float(selected[CONF_COLD_W]),
                night_start=22 if tariff == "G12w" or 4 <= now.month <= 9 else 21,
                night_end=6 if tariff == "G12w" else 7,
                midday_start=13,
                afternoon_end=15 if tariff == "G12w" else 19 if 4 <= now.month <= 9 else 16,
            )
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as err:
            _LOGGER.error("Cannot calculate energy plan: %s", err)
            return {**history, "available": False,
                    "reason": "Błędne ustawienia — sprawdź konfigurację"}
        # Independent 48-hour forecast. Never issue inverter commands here.
        # Current EV draw is included ONLY in the first 15-minute slot:
        # future sessions cannot be deduced from the instantaneous reading.
        try:
            simulation = simulate_48h(
                now=now, pv_slots=pv_slots, temps=temperatures, learning=learned,
                model=model, start_soc=soc, current_temp=outdoor_temp,
                tariff=tariff, baseload_w=float(selected[CONF_BASE_W]),
                mild_w=float(selected[CONF_MILD_W]),
                cold_w=float(selected[CONF_COLD_W]),
                pv_discount_pct=float(selected[CONF_PV_DISCOUNT]),
                efficiency_pct=float(selected[CONF_EFFICIENCY]),
                battery_max_kw=float(selected[CONF_CHARGE_LIMIT]),
                grid_limit_kw=float(selected[CONF_GRID_LIMIT]),
                ev_now_kw=self._kw_or_none(CONF_EV_POWER),
                prices=prices,
            )
            v2_info["simulation_48h"] = simulation
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as err:
            _LOGGER.warning("48h simulation unavailable: %s", err)
            v2_info["simulation_48h"] = {
                "status": "blad_danych",
                "reason": f"Nie można obliczyć symulacji: {type(err).__name__}",
                "timeline_hours": [],
                "forecast_hours": 0,
            }
        # Old energy windows use a simple daily model. Weekend planning and
        # household learning will be implemented by the 48h simulation engine.
        if tariff_window and not is_day_off(tariff_window[0].date()):
            target_plan = (
                plan["afternoon"] if tariff_window[0].hour == 13
                else plan["night"]
            )
            if target_plan.can_calculate:
                adjusted = round(model.adjusted_target(target_plan.target_soc))
                target_plan = replace(target_plan, target_soc=adjusted)
                if tariff_window[0].hour == 13:
                    plan["afternoon"] = target_plan
                else:
                    plan["night"] = target_plan
                proposed = propose(
                    now=now, window=tariff_window, soc=soc,
                    target=adjusted, model=model,
                    grid_headroom_kw=guard.allowed_charge_kw,
                    power_limit_kw=float(selected[CONF_CHARGE_LIMIT]),
                    preferred_kw=float(selected[CONF_PREFERRED_CHARGE]),
                    efficiency=float(selected[CONF_EFFICIENCY]) / 100,
                )
                v2_info["charging_schedule"] = proposed.as_dict()
        else:
            v2_info["schedule_note"] = (
                "Dzień wolny lub brak taniego okna — wymagany pełny symulator 48h"
            )
        v2_info["current_soc_pct"] = round(soc, 1)
        # Never advertise a charging decision while grid polarity is
        # unverified, when limits are unknown, or on whole-day cheap holidays.
        plan["recommended"] = bool(
            plan.get("recommended") and guard.allowed_charge_kw is not None
            and guard.allowed_charge_kw >= 3
            and tariff_band == "cheap" and not is_day_off(now.date())
        )
        plan.update(history)
        plan["available"] = True
        plan["temperature_source"] = "hourly" if temperatures else temperature_source
        plan["current_soc"] = round(soc, 1)
        return plan
