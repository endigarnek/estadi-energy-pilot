"""Home Assistant discovery of the built-in Forecast.Solar configuration."""
from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from .const import CONF_FORECAST_SOLAR_ENTRY
from .forecast_source import choose_forecast_entry


def available_entries(hass):
    return list(hass.config_entries.async_entries("forecast_solar"))


def preferred_entry(hass, stored: str | None = None) -> str | None:
    entries = available_entries(hass)
    ids = [entry.entry_id for entry in entries]

    # The user's existing sensor.energy_production_today belongs to one
    # Forecast.Solar entry. Prefer that concrete connection over an arbitrary
    # first element when more than one forecast configuration exists.
    registry = er.async_get(hass)
    primary = registry.async_get("sensor.energy_production_today")
    linked = getattr(primary, "config_entry_id", None) if primary else None
    return choose_forecast_entry(ids, linked_sensor_entry=linked, stored_entry=stored)


def forecast_config_schema(hass, stored: str | None = None):
    """Purely label values for an optional multi-entry dropdown."""
    return {entry.entry_id: entry.title or f"Forecast.Solar {i + 1}"
            for i, entry in enumerate(available_entries(hass))}
