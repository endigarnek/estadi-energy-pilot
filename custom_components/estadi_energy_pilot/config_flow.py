"""Simple Polish UI wizard and advanced tuning for ESTADI Energy Pilot."""
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
    CONF_CAPACITY, CONF_BASE_W, CONF_RESERVE, CONF_MAX_SOC,
    CONF_PV_DISCOUNT, CONF_EFFICIENCY, CONF_MARGIN, CONF_MILD_W, CONF_COLD_W,
    CONF_NIGHT_START, CONF_NIGHT_END, CONF_MIDDAY_START, CONF_AFTERNOON_END,
)


def entity_field(domain: str = "sensor") -> EntitySelector:
    return EntitySelector(EntitySelectorConfig(domain=domain, multiple=False))


def numeric(minimum: float, maximum: float, step: float = 1.0) -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=minimum, max=maximum, step=step,
                                                mode=NumberSelectorMode.BOX))


class EstadiEnergyPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """First setup contains only a few required sensors and two numbers."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id("main")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="ESTADI Energy Pilot", data={**DEFAULTS, **user_input})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_SOLCAST_TODAY): entity_field(),
            vol.Required(CONF_SOLCAST_TOMORROW): entity_field(),
            vol.Optional(CONF_SOLCAST_DAY3): entity_field(),
            vol.Required(CONF_BATTERY_SOC): entity_field(),
            vol.Required(CONF_OUTDOOR_TEMP): entity_field(),
            vol.Optional(CONF_WEATHER): entity_field("weather"),
            vol.Required(CONF_CAPACITY, default=DEFAULTS[CONF_CAPACITY]): numeric(1, 200, 0.1),
            vol.Required(CONF_BASE_W, default=DEFAULTS[CONF_BASE_W]): numeric(0, 20000, 50),
        }))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PilotOptionsFlow:
        return PilotOptionsFlow()


class PilotOptionsFlow(OptionsFlow):
    """Editing tariff, reserve, PV risk and heat model from HA Configure."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if (user_input[CONF_RESERVE] >= user_input[CONF_MAX_SOC]
                    or user_input[CONF_NIGHT_END] >= user_input[CONF_MIDDAY_START]
                    or user_input[CONF_MIDDAY_START] >= user_input[CONF_AFTERNOON_END]
                    or user_input[CONF_AFTERNOON_END] >= user_input[CONF_NIGHT_START]):
                return self.async_show_form(step_id="init", data_schema=self._schema(),
                                            errors={"base": "invalid_schedule"})
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=self._schema())

    def _schema(self):
        values = {**self.config_entry.data, **self.config_entry.options}
        return vol.Schema({
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
        })
