"""Safely register/refresh ONLY ESTADI's Lovelace JS resource.

The user explicitly opted into the managed dashboard via the generator.
Home Assistant stores Lovelace resource URLs with long browser caching, so
newly-added custom card types require a versioned URL after HACS updates.

Safety requirements:
- Always load resource storage before listing/updating/creating to avoid losing
  unrelated Lovelace resources on older HA versions.
- Never modify another project's resource, a YAML-managed resource, or a
  duplicate/ambiguous ESTADI registration.
- Never touch the inverter or change existing dashboards.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

from .dashboard_export import FORECAST_CARD_JS, FORECAST_CARD_RESOURCE

_LOGGER = logging.getLogger(__name__)


def is_estadi_resource(url: object) -> bool:
    """Match only the exact local resource path, allowing a version query."""
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return (
        not parsed.scheme and not parsed.netloc and
        parsed.path == "/local/" + FORECAST_CARD_JS
    )


async def async_ensure_estadi_resource(hass) -> dict[str, str]:
    """Create/update the opt-in ESTADI resource, never unrelated resources.

    This is intended after a successful managed export (file exists) and not
    for arbitrary integration startup with no managed manifest.
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return {"status": "lovelace_unavailable", "url": FORECAST_CARD_RESOURCE}
    if getattr(lovelace, "resource_mode", None) == "yaml":
        return {"status": "yaml_resources_manual", "url": FORECAST_CARD_RESOURCE}
    resources = getattr(lovelace, "resources", None)
    if resources is None or not callable(getattr(resources, "async_get_info", None)):
        return {"status": "resources_unavailable", "url": FORECAST_CARD_RESOURCE}

    # CRITICAL: load resources from disk before calling async_items/create.
    # Some HA versions lazily initialize this collection.
    await resources.async_get_info()
    matches = [item for item in resources.async_items()
               if is_estadi_resource(item.get("url"))]
    if len(matches) > 1:
        _LOGGER.warning("ESTADI: wykryto wiele zasobów kart — nie zmieniono żadnego")
        return {"status": "duplicate_resources", "url": FORECAST_CARD_RESOURCE}

    if not matches:
        await resources.async_create_item(
            {"url": FORECAST_CARD_RESOURCE, "res_type": "module"}
        )
        return {"status": "registered", "url": FORECAST_CARD_RESOURCE}

    item = matches[0]
    if item.get("url") == FORECAST_CARD_RESOURCE and item.get("type") == "module":
        return {"status": "ready", "url": FORECAST_CARD_RESOURCE}
    if not item.get("id"):
        return {"status": "resource_id_missing", "url": FORECAST_CARD_RESOURCE}
    await resources.async_update_item(
        item["id"], {"url": FORECAST_CARD_RESOURCE, "res_type": "module"}
    )
    return {"status": "updated", "url": FORECAST_CARD_RESOURCE}
