"""Offline regression coverage of source validation and empty override recovery."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

FILE = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/source_diagnostics.py"
spec = importlib.util.spec_from_file_location("estadi_diagnostics", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def s(value, unit="%"):
    return SimpleNamespace(state=str(value), attributes={"unit_of_measurement": unit})


class SourceDiagnosticsTests(unittest.TestCase):
    def test_soc_valid(self):
        self.assertEqual(module.read_numeric(s(57), "%", 0, 100), (57, "OK"))

    def test_soc_wrong_unit(self):
        value, reason = module.read_numeric(s(57, "V"), "%", 0, 100)
        self.assertIsNone(value)
        self.assertIn("jednostka", reason)

    def test_soc_unknown_and_invalid(self):
        value, reason = module.read_numeric(s("unavailable"), "%", 0, 100)
        self.assertIsNone(value)
        self.assertIn("unavailable", reason)
        self.assertIsNone(module.read_numeric(s(101), "%", 0, 100)[0])

    def test_temperature_valid(self):
        self.assertEqual(module.read_numeric(s(4, "°C"), "°C", -70, 65), (4, "OK"))

    def test_old_empty_options_must_not_override_detection(self):
        sources = {"battery_soc": "sensor.deye_battery", "weather_entity": "weather.dom"}
        stored = {"battery_soc": "", "weather_entity": "", "pv_power": "sensor.deye_pv_power"}
        selected = module.select_nonempty_sources(sources, stored)
        self.assertEqual(selected["battery_soc"], "sensor.deye_battery")
        self.assertEqual(selected["weather_entity"], "weather.dom")
        self.assertEqual(selected["pv_power"], "sensor.deye_pv_power")


if __name__ == "__main__":
    unittest.main()
