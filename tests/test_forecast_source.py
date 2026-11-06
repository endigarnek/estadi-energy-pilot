"""Offline tests for Forecast.Solar hourly get_forecast service responses."""
import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot"
package = types.ModuleType("forecast_source_test")
package.__path__ = [str(ROOT)]
sys.modules["forecast_source_test"] = package

for name in ("engine", "forecast_source", "const", "discovery"):
    spec = importlib.util.spec_from_file_location(f"forecast_source_test.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

src = sys.modules["forecast_source_test.forecast_source"]
engine = sys.modules["forecast_source_test.engine"]
discovery = sys.modules["forecast_source_test.discovery"]
const = sys.modules["forecast_source_test.const"]


class TestForecastSolar(unittest.TestCase):
    def test_wh_period_hourly_wh_to_kwh(self):
        raw = {
            "watts": {
                "2026-11-07T09:00:00+01:00": 2000,
                "2026-11-07T10:00:00+01:00": 3200,
            },
            "wh_period": {
                "2026-11-07T09:00:00+01:00": 1800,
                "2026-11-07T10:00:00+01:00": 3000,
            },
        }
        slots = src.parse_forecast_solar_response(raw)
        self.assertEqual(len(slots), 2)
        self.assertEqual([slot.duration_minutes for slot in slots], [60, 60])
        self.assertEqual([slot.power_kw for slot in slots], [1.8, 3.0])
        p = engine.plan_window(
            "day", datetime(2026, 11, 7, 9, tzinfo=timezone.utc),
            datetime(2026, 11, 7, 11, tzinfo=timezone.utc),
            slots, [], 15, 20, 400, 20, 95, 0, 90, 1, 600, 1200
        )
        self.assertAlmostEqual(p.pv_kwh, 4.8)

    def test_bad_response_not_equivalent_to_zero_forecast(self):
        self.assertEqual(src.parse_forecast_solar_response(None), [])
        self.assertEqual(src.parse_forecast_solar_response({"invalid": True}), [])
        self.assertEqual(src.parse_forecast_solar_response({
            "wh_period": {"not-a-time": 123, "2026-11-07T09:00:00+01:00": -10}
        }), [])

    def test_watts_fallback(self):
        raw = {"watts": {"2026-11-07T08:00:00+01:00": 700}}
        slots = src.parse_forecast_solar_response(raw)
        self.assertEqual(slots[0].power_kw, 0.7)

    def test_single_entry_auto_selected(self):
        self.assertEqual(src.choose_forecast_entry(["entry-1"]), "entry-1")

    def test_two_entries_use_primary_sensor_link(self):
        self.assertEqual(
            src.choose_forecast_entry(["plant-1", "plant-2"], linked_sensor_entry="plant-2"),
            "plant-2",
        )

    def test_ambiguous_entries_never_guessed(self):
        self.assertIsNone(src.choose_forecast_entry(["plant-1", "plant-2"]))

    def test_stored_entry_wins(self):
        self.assertEqual(src.choose_forecast_entry(
            ["plant-1", "plant-2"], linked_sensor_entry="plant-1",
            stored_entry="plant-2",
        ), "plant-2")

    def test_forecast_solar_skips_solcast_fields(self):
        missing = discovery.missing_required_sources({}, forecast_solar_available=True)
        self.assertNotIn(const.CONF_SOLCAST_TODAY, missing)
        self.assertNotIn(const.CONF_SOLCAST_TOMORROW, missing)
        self.assertIn(const.CONF_BATTERY_SOC, missing)
        self.assertIn(const.CONF_OUTDOOR_TEMP, missing)


if __name__ == "__main__":
    unittest.main()
