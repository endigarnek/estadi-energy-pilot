"""Regression: HA Lovelace cache-busted resource without touching other entries."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PKG = "energy_resource_regression"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


dashboard = load("dashboard_export")
resource = load("lovelace_resource")


class FakeResources:
    def __init__(self, items):
        self.loaded = False
        self.items = [dict(item) for item in items]
        self.events = []

    async def async_get_info(self):
        self.loaded = True
        self.events.append("load")
        return {"resources": len(self.items)}

    def async_items(self):
        assert self.loaded, "Unloaded resource list could erase HA resources"
        self.events.append("read")
        return list(self.items)

    async def async_create_item(self, data):
        assert self.loaded
        self.events.append("create")
        self.items.append({"id": "new", "type": data["res_type"], "url": data["url"]})

    async def async_update_item(self, entity_id, values):
        assert self.loaded
        self.events.append("update")
        for item in self.items:
            if item.get("id") == entity_id:
                item.update(url=values["url"], type=values["res_type"])
                return
        raise KeyError(entity_id)


class ResourceTests(unittest.IsolatedAsyncioTestCase):
    def ha(self, items, mode="storage"):
        entries = FakeResources(items)
        lovelace = types.SimpleNamespace(resource_mode=mode, resources=entries)
        hass = types.SimpleNamespace(data={"lovelace": lovelace})
        return hass, entries

    async def test_only_old_estadi_url_updated_and_unrelated_resources_unchanged(self):
        own = {"id": "estadi1", "url": "/local/estadi-energy-pilot-ui-v046.js", "type": "module"}
        other = {"id": "other", "url": "/hacsfiles/other-card/other.js?v=42", "type": "module"}
        hass, db = self.ha([own, other])
        result = await resource.async_ensure_estadi_resource(hass)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(db.events, ["load", "read", "update"])
        self.assertEqual(db.items[1], other)
        self.assertEqual(db.items[0]["url"], dashboard.FORECAST_CARD_RESOURCE)

    async def test_versioned_url_is_idempotent(self):
        own = {"id": "mycard", "url": dashboard.FORECAST_CARD_RESOURCE, "type": "module"}
        hass, db = self.ha([own])
        result = await resource.async_ensure_estadi_resource(hass)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(db.events, ["load", "read"])

    async def test_one_missing_resource_is_created_only_after_loading_collection(self):
        other = {"id": "other", "url": "/local/calendar-card.js", "type": "module"}
        hass, db = self.ha([other])
        result = await resource.async_ensure_estadi_resource(hass)
        self.assertEqual(result["status"], "registered")
        self.assertEqual(db.events, ["load", "read", "create"])
        self.assertEqual(db.items[0], other)
        self.assertEqual(db.items[1]["url"], dashboard.FORECAST_CARD_RESOURCE)

    async def test_two_estadi_resources_not_mutated(self):
        hass, db = self.ha([
            {"id": "one", "url": "/local/estadi-energy-pilot-ui-v046.js", "type": "module"},
            {"id": "two", "url": dashboard.FORECAST_CARD_RESOURCE, "type": "module"},
        ])
        result = await resource.async_ensure_estadi_resource(hass)
        self.assertEqual(result["status"], "duplicate_resources")
        self.assertEqual(db.events, ["load", "read"])

    async def test_yaml_resource_mode_not_modified(self):
        hass, db = self.ha([], mode="yaml")
        result = await resource.async_ensure_estadi_resource(hass)
        self.assertEqual(result["status"], "yaml_resources_manual")
        self.assertEqual(db.events, [])

    async def test_lovelace_is_not_loaded_leaves_resources_untouched(self):
        h = types.SimpleNamespace(data={})
        result = await resource.async_ensure_estadi_resource(h)
        self.assertEqual(result["status"], "lovelace_unavailable")

    async def test_only_exact_filename_can_be_matched(self):
        self.assertTrue(resource.is_estadi_resource("/local/estadi-energy-pilot-ui-v046.js?v=0.4.6"))
        self.assertFalse(resource.is_estadi_resource("/local/estadi-energy-pilot-ui-v046.js.evil"))
        self.assertFalse(resource.is_estadi_resource("https://example.test/local/estadi-energy-pilot-ui-v046.js"))
        self.assertFalse(resource.is_estadi_resource("/local/other.js"))

    async def test_resource_version_matches_manifest(self):
        version = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
        self.assertTrue(dashboard.FORECAST_CARD_RESOURCE.endswith("?v=" + version))


if __name__ == "__main__":
    unittest.main()
