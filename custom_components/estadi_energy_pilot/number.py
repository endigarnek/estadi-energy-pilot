"""Editable battery capacity and reserve bias; never send hardware commands."""
from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN, DEFAULTS, CONF_NOMINAL_KWH, CONF_CORRECTION

NUMBER_CONFIG = {
    CONF_NOMINAL_KWH: ("Pojemność nominalna magazynu", 1, 200, 0.1, "kWh"),
    CONF_CORRECTION: ("Korekta zapasu SOC", -15, 15, 1, "%"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PilotConfigNumber(hass, entry, key) for key in NUMBER_CONFIG])


class PilotConfigNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hass, entry, key):
        self.hass = hass
        self.entry = entry
        self.key = key
        title, lower, upper, step, unit = NUMBER_CONFIG[key]
        self._attr_name = title
        self._attr_unique_id = f"{entry.entry_id}_config_{key}"
        self._attr_native_min_value = lower
        self._attr_native_max_value = upper
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "ESTADI Energy Pilot",
            "manufacturer": "ESTADI",
        }

    @property
    def native_value(self):
        return self.entry.options.get(self.key, self.entry.data.get(self.key, DEFAULTS[self.key]))

    async def async_set_native_value(self, value: float) -> None:
        if not self.native_min_value <= value <= self.native_max_value:
            raise ValueError("Wartość poza zakresem")
        # HA config entry options are persistent; its listener recalculates the plan.
        options = {**self.entry.options, self.key: float(value)}
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.async_write_ha_state()
