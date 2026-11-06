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
)
from .discovery import detect_entities


ENTITY_KEYS = (
    CONF_PV_POWER, CONF_HOME_POWER, CONF_HEAT_PUMP_POWER, CONF_EV_POWER,
    CONF_BATTERY_SOC, CONF_OUTDOOR_TEMP, CONF_SOLCAST_TODAY,
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
        if user_input is not None:
            await self.async_set_unique_id("main")
            self._abort_if_unique_id_configured()
            # Persist known sensors as soon as the user confirms the setup.
            return self.async_create_entry(
                title="ESTADI Energy Pilot",
                data={**DEFAULTS, **detected, **user_input},
            )

        schema = {}
        required = (CONF_SOLCAST_TODAY, CONF_SOLCAST_TOMORROW,
                    CONF_BATTERY_SOC, CONF_OUTDOOR_TEMP)
        for key in required:
            if not detected.get(key):
                schema[vol.Required(key)] = entity_field()

        schema[vol.Required(CONF_CAPACITY, default=DEFAULTS[CONF_CAPACITY])] = numeric(1, 200, 0.1)
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
    """Change sensors and energy settings without removing the integration."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if (user_input[CONF_RESERVE] >= user_input[CONF_MAX_SOC]
                    or user_input[CONF_NIGHT_END] >= user_input[CONF_MIDDAY_START]
                    or user_input[CONF_MIDDAY_START] >= user_input[CONF_AFTERNOON_END]
                    or user_input[CONF_AFTERNOON_END] >= user_input[CONF_NIGHT_START]):
                return self.async_show_form(step_id="init", data_schema=self._schema(),
                                            errors={"base": "invalid_schedule"})
            # An explicitly cleared entity must not silently fall back to a stale saved ID.
            options = {**self.config_entry.options, **user_input}
            for key in ENTITY_KEYS:
                if key not in user_input and (key in self.config_entry.options or key in self.config_entry.data):
                    options[key] = ""
            return self.async_create_entry(data=options)
        return self.async_show_form(step_id="init", data_schema=self._schema())

    def _schema(self):
        values = {
            **DEFAULTS,
            **suggested_entities(self.hass),
            **self.config_entry.data,
            **self.config_entry.options,
        }
        schema = {
            vol.Required(CONF_CAPACITY, default=values[CONF_CAPACITY]): numeric(1, 200, 0.1),
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
        return vol.Schema(schema)
