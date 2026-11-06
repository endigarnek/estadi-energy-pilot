import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/weather_temperature.py"
spec = importlib.util.spec_from_file_location("energy_weather_temperature", ROOT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def state(temp, unit="°C", status="cloudy"):
    return SimpleNamespace(state=status, attributes={
        "temperature": temp, "temperature_unit": unit})


class WeatherTemperatureTests(unittest.TestCase):
    def test_current_weather_celsius(self):
        self.assertEqual(module.weather_temperature_c(state(4)), 4)

    def test_current_weather_fahrenheit(self):
        self.assertAlmostEqual(module.weather_temperature_c(state(39.2, "°F")), 4)

    def test_unavailable_weather_not_interpreted_as_zero(self):
        self.assertIsNone(module.weather_temperature_c(state(0, status="unavailable")))

    def test_untrusted_units_and_missing_values(self):
        self.assertIsNone(module.weather_temperature_c(state(280, "K")))
        self.assertIsNone(module.weather_temperature_c(state(None)))

    def test_nonfinite_and_impossible_temperatures(self):
        self.assertIsNone(module.weather_temperature_c(state(float("nan"))))
        self.assertIsNone(module.weather_temperature_c(state(600)))


if __name__ == "__main__":
    unittest.main()
