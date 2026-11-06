"""Advisory flag only, not an actuator."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ChargeRecommendation(hass.data[DOMAIN][entry.entry_id], entry)])


class ChargeRecommendation(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "ESTADI Energy Pilot Zalecane ładowanie"
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_charge_recommended"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "ESTADI Energy Pilot"}

    @property
    def is_on(self):
        data = self.coordinator.data
        return bool(data and data.get("available") and data.get("recommended"))
