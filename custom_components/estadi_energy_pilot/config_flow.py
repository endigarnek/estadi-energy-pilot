"""Polish setup wizard with automatic selection of existing HA entities."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector, EntitySelectorConfig, NumberSelector,
    NumberSelectorConfig, NumberSelectorMode,
)

from .const import (
    DOMAIN, DEFAULTS, CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW,
    CONF_SOLCAST_DAY3, CONF_BATTERY_SOC, CONF_OUTDOOR_TEMP, CONF_WEATHER,
    CONF_PV_POWER, CONF_HOME_POWER, CONF_HEAT_PUMP_POWER, CONF_EV_POWER,
    CONF_CAPACITY, CONF_BASE_W, CONF_RESERVE, CONF_MAX_SOC,
    CONF_PV_DISCOUNT, CONF_EFFICIENCY, CONF_MARGIN, CONF_MILD_W, CONF_COLD_W,
    CONF_NIGHT_START, CONF_NIGHT_END, CONF_MIDDAY_START, CONF_AFTERNOON_END,
    CONF_FORECAST_SOLAR_ENTRY,
    CONF_NOMINAL_KWH, CONF_SOH, CONF_MIN_SOC, CONF_USER_MAX_SOC,
    CONF_CORRECTION, CONF_GRID_POWER, CONF_GRID_LIMIT, CONF_GRID_BUFFER,
    CONF_GRID_IMPORT_SIGN, CONF_CHARGE_LIMIT, CONF_PREFERRED_CHARGE,
    CONF_TARIFF, CONF_PRICE_CHEAP, CONF_PRICE_PEAK, CONF_PRICE_EVENING,
)
from .discovery import detect_entities, missing_required_sources
from .forecast_entry import available_entries, preferred_entry, forecast_config_schema


ENTITY_KEYS = (
    CONF_PV_POWER, CONF_HOME_POWER, CONF_HEAT_PUMP_POWER, CONF_EV_POWER,
    CONF_GRID_POWER, CONF_BATTERY_SOC, CONF_OUTDOOR_TEMP, CONF_SOLCAST_TODAY,
    CONF_SOLCAST_TOMORROW, CONF_SOLCAST_DAY3, CONF_WEATHER,
)


def entity_field(domain: str = "sensor") -> EntitySelector:
    return EntitySelector(EntitySelectorConfig(domain=domain, multiple=False))


def numeric(minimum: float, maximum: float, step: float = 1.0) -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=minimum, max=maximum, step=step,
                                                mode=NumberSelectorMode.BOX))


def _entity_fields(values: dict) -> dict:
    """Supply Voluptuous defaults only when an entity was saved or detected."""
    fields = {}
    for key in ENTITY_KEYS:
        current = values.get(key)
        field = vol.Optional(key, default=current) if current else vol.Optional(key)
        fields[field] = entity_field("weather" if key == CONF_WEATHER else "sensor")
    return fields


def suggested_entities(hass, stored: dict | None = None) -> dict:
    """Previously chosen sensors take priority over automatic suggestions."""
    return {**detect_entities(hass.states.async_all()), **(stored or {})}


class EstadiEnergyPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Select already installed sensors by default — no manual entity hunting."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Only show missing required entity IDs, never all known sensors."""
        detected = suggested_entities(self.hass)
        forecast_entries = available_entries(self.hass)
        selected_forecast = preferred_entry(self.hass)
        if selected_forecast:
            detected[CONF_FORECAST_SOLAR_ENTRY] = selected_forecast
        if user_input is not None:
            await self.async_set_unique_id("main")
            self._abort_if_unique_id_configured()
            # Persist known sensors as soon as the user confirms the setup.
            return self.async_create_entry(
                title="ESTADI Energy Pilot",
                data={**DEFAULTS, **detected, **user_input},
            )

        schema = {}
        for key in missing_required_sources(
            detected, forecast_solar_available=bool(forecast_entries)
        ):
            if not detected.get(key):
                schema[vol.Required(key)] = entity_field()

        if forecast_entries and selected_forecast is None:
            # Multiple Forecast.Solar entries: do not silently choose a roof.
            schema[vol.Required(CONF_FORECAST_SOLAR_ENTRY)] = vol.In(
                forecast_config_schema(self.hass)
            )
        schema[vol.Required(CONF_NOMINAL_KWH, default=28)] = numeric(1, 200, 0.1)
        schema[vol.Required(CONF_BASE_W, default=DEFAULTS[CONF_BASE_W])] = numeric(0, 20000, 50)

        known = [detected[key] for key in ENTITY_KEYS if key in detected]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "detected_count": str(len(known)),
                "detected_entities": ", ".join(known) if known else "—",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PilotOptionsFlow:
        return PilotOptionsFlow()


class PilotOptionsFlow(OptionsFlow):
    """Simple settings first; manual configuration only on request."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            submitted = dict(user_input)
            show_advanced = submitted.pop("advanced", False)
            if show_advanced:
                self._quick_changes = submitted
                return await self.async_step_advanced()
            if submitted[CONF_MIN_SOC] >= submitted[CONF_USER_MAX_SOC]:
                return self.async_show_form(
                    step_id="init", data_schema=self._quick_schema(),
                    errors={"base": "invalid_battery"},
                    description_placeholders={"detected_count": str(len(suggested_entities(self.hass)))},
                )
            return self.async_create_entry(
                data={**self.config_entry.options, **submitted},
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self._quick_schema(),
            description_placeholders={
                "detected_count": str(len(suggested_entities(self.hass))),
            },
        )

    def _quick_schema(self):
        values = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}
        return vol.Schema({
            vol.Required(CONF_NOMINAL_KWH, default=values[CONF_NOMINAL_KWH]): numeric(1, 200, 0.1),
            vol.Required(CONF_MIN_SOC, default=values[CONF_MIN_SOC]): numeric(0, 95, 1),
            vol.Required(CONF_USER_MAX_SOC, default=values[CONF_USER_MAX_SOC]): numeric(10, 100, 1),
            vol.Required(CONF_GRID_LIMIT, default=values[CONF_GRID_LIMIT]): numeric(1, 40, 0.1),
            vol.Required(CONF_TARIFF, default=values[CONF_TARIFF]): vol.In(("G12w", "G13")),
            vol.Required(CONF_CORRECTION, default=values[CONF_CORRECTION]): numeric(-15, 15, 1),
            vol.Optional("advanced", default=False): bool,
        })

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            proposed = {
                **DEFAULTS,
                **self.config_entry.data,
                **self.config_entry.options,
                **getattr(self, "_quick_changes", {}),
                **user_input,
            }
            if (proposed[CONF_MIN_SOC] >= proposed[CONF_USER_MAX_SOC]
                    or proposed[CONF_GRID_BUFFER] >= proposed[CONF_GRID_LIMIT]
                    or proposed[CONF_PREFERRED_CHARGE] > proposed[CONF_CHARGE_LIMIT]
                    or proposed[CONF_RESERVE] >= proposed[CONF_MAX_SOC]
                    or proposed[CONF_NIGHT_END] >= proposed[CONF_MIDDAY_START]
                    or proposed[CONF_MIDDAY_START] >= proposed[CONF_AFTERNOON_END]
                    or proposed[CONF_AFTERNOON_END] >= proposed[CONF_NIGHT_START]):
                return self.async_show_form(
                    step_id="advanced",
                    data_schema=self._schema(),
                    errors={"base": "invalid_schedule"},
                )
            options = {**self.config_entry.options,
                       **getattr(self, "_quick_changes", {}), **user_input}
            # In advanced mode an omitted optional field is an intentional clear.
            for key in ENTITY_KEYS:
                if key not in user_input and (
                    key in self.config_entry.options or key in self.config_entry.data
                ):
                    options[key] = ""
            return self.async_create_entry(data=options)
        return self.async_show_form(step_id="advanced", data_schema=self._schema())

    def _schema(self):
        values = {
            **DEFAULTS,
            **suggested_entities(self.hass),
            **self.config_entry.data,
            **self.config_entry.options,
            **getattr(self, "_quick_changes", {}),
        }
        schema = {
            vol.Required(CONF_NOMINAL_KWH, default=values[CONF_NOMINAL_KWH]): numeric(1, 200, 0.1),
            vol.Required(CONF_SOH, default=values[CONF_SOH]): numeric(50, 100, 0.5),
            vol.Required(CONF_MIN_SOC, default=values[CONF_MIN_SOC]): numeric(0, 95, 1),
            vol.Required(CONF_USER_MAX_SOC, default=values[CONF_USER_MAX_SOC]): numeric(10, 100, 1),
            vol.Required(CONF_CORRECTION, default=values[CONF_CORRECTION]): numeric(-15, 15, 1),
            vol.Required(CONF_GRID_LIMIT, default=values[CONF_GRID_LIMIT]): numeric(1, 40, 0.1),
            vol.Required(CONF_GRID_BUFFER, default=values[CONF_GRID_BUFFER]): numeric(0, 10, 0.1),
            vol.Required(CONF_GRID_IMPORT_SIGN, default=values[CONF_GRID_IMPORT_SIGN]): vol.In({
                0: "Niepotwierdzony znak importu",
                1: "Wartość dodatnia oznacza import",
                -1: "Wartość ujemna oznacza import",
            }),
            vol.Required(CONF_CHARGE_LIMIT, default=values[CONF_CHARGE_LIMIT]): numeric(1, 20, 0.5),
            vol.Required(CONF_PREFERRED_CHARGE, default=values[CONF_PREFERRED_CHARGE]): numeric(1, 20, 0.5),
            vol.Required(CONF_TARIFF, default=values[CONF_TARIFF]): vol.In(("G12w", "G13")),
            vol.Required(CONF_PRICE_CHEAP, default=values[CONF_PRICE_CHEAP]): numeric(0, 10, 0.01),
            vol.Required(CONF_PRICE_PEAK, default=values[CONF_PRICE_PEAK]): numeric(0, 10, 0.01),
            vol.Required(CONF_PRICE_EVENING, default=values[CONF_PRICE_EVENING]): numeric(0, 10, 0.01),
            vol.Required(CONF_BASE_W, default=values[CONF_BASE_W]): numeric(0, 20000, 50),
            vol.Required(CONF_RESERVE, default=values[CONF_RESERVE]): numeric(5, 80),
            vol.Required(CONF_MAX_SOC, default=values[CONF_MAX_SOC]): numeric(20, 100),
            vol.Required(CONF_PV_DISCOUNT, default=values[CONF_PV_DISCOUNT]): numeric(0, 60),
            vol.Required(CONF_EFFICIENCY, default=values[CONF_EFFICIENCY]): numeric(50, 100),
            vol.Required(CONF_MARGIN, default=values[CONF_MARGIN]): numeric(0, 10, 0.1),
            vol.Required(CONF_MILD_W, default=values[CONF_MILD_W]): numeric(0, 8000, 50),
            vol.Required(CONF_COLD_W, default=values[CONF_COLD_W]): numeric(0, 12000, 50),
            vol.Required(CONF_NIGHT_START, default=values[CONF_NIGHT_START]): numeric(17, 23),
            vol.Required(CONF_NIGHT_END, default=values[CONF_NIGHT_END]): numeric(1, 12),
            vol.Required(CONF_MIDDAY_START, default=values[CONF_MIDDAY_START]): numeric(10, 16),
            vol.Required(CONF_AFTERNOON_END, default=values[CONF_AFTERNOON_END]): numeric(11, 20),
        }
        schema.update(_entity_fields(values))
        forecast_entries = available_entries(self.hass)
        if forecast_entries:
            saved = values.get(CONF_FORECAST_SOLAR_ENTRY)
            preferred = preferred_entry(self.hass, stored=saved)
            marker = (vol.Optional(CONF_FORECAST_SOLAR_ENTRY, default=preferred)
                      if preferred else vol.Optional(CONF_FORECAST_SOLAR_ENTRY))
            schema[marker] = vol.In(forecast_config_schema(self.hass))
        return vol.Schema(schema)
