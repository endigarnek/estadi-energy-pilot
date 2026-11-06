"""Entity detection must select real, correctly typed entities without guessing."""
import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot"
package = types.ModuleType("autodetect_test")
package.__path__ = [str(ROOT)]
sys.modules["autodetect_test"] = package
for name in ("const", "discovery"):
    spec = importlib.util.spec_from_file_location(f"autodetect_test.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
const = sys.modules["autodetect_test.const"]
detect_entities = sys.modules["autodetect_test.discovery"].detect_entities
missing_required_sources = sys.modules["autodetect_test.discovery"].missing_required_sources


class FakeState:
    def __init__(self, entity_id, unit=None, **attributes):
        self.entity_id = entity_id
        self.attributes = {"unit_of_measurement": unit, **attributes}


class TestDetectEntities(unittest.TestCase):
    def test_user_exact_entities_are_preset(self):
        states = [
            FakeState("sensor.deye_pv_power", "W"),
            FakeState("sensor.deye_load_power", "W"),
            FakeState("sensor.shellyem3_08f9e051e0b0_channel_b_power", "W"),
            FakeState("sensor.moc_ladowarki_poprawna", "W"),
        ]
        selected = detect_entities(states)
        self.assertEqual(selected[const.CONF_PV_POWER], "sensor.deye_pv_power")
        self.assertEqual(selected[const.CONF_HOME_POWER], "sensor.deye_load_power")
        self.assertEqual(selected[const.CONF_HEAT_PUMP_POWER],
                         "sensor.shellyem3_08f9e051e0b0_channel_b_power")
        self.assertEqual(selected[const.CONF_EV_POWER], "sensor.moc_ladowarki_poprawna")

    def test_no_nonexistent_or_mismatched_units(self):
        selected = detect_entities([
            FakeState("sensor.deye_pv_power", "kWh"),
            FakeState("sensor.moc_ladowarki_poprawna", "A"),
        ])
        self.assertNotIn(const.CONF_PV_POWER, selected)
        self.assertNotIn(const.CONF_EV_POWER, selected)

    def test_soc_only_if_valid_and_unambiguous(self):
        selected = detect_entities([FakeState("sensor.deye_battery_soc", "%")])
        self.assertEqual(selected[const.CONF_BATTERY_SOC], "sensor.deye_battery_soc")
        selected = detect_entities([
            FakeState("sensor.deye_1_battery_soc", "%"),
            FakeState("sensor.deye_2_battery_soc", "%"),
        ])
        self.assertNotIn(const.CONF_BATTERY_SOC, selected)

    def test_weather_unique_and_outdoor_temperature(self):
        selected = detect_entities([
            FakeState("sensor.temperatura_zewnetrzna", "°C"),
            FakeState("weather.home"),
        ])
        self.assertEqual(selected[const.CONF_OUTDOOR_TEMP], "sensor.temperatura_zewnetrzna")
        self.assertEqual(selected[const.CONF_WEATHER], "weather.home")
        self.assertNotIn(const.CONF_OUTDOOR_TEMP, detect_entities(
            [FakeState("sensor.outdoor_temperature", "°F")]))

    def test_detects_solcast_with_detailed_forecast(self):
        selected = detect_entities([
            FakeState("sensor.solcast_pv_forecast_forecast_today", "kWh", detailedForecast=[]),
            FakeState("sensor.solcast_pv_forecast_forecast_tomorrow", "kWh", detailedHourly=[]),
        ])
        self.assertEqual(selected[const.CONF_SOLCAST_TODAY],
                         "sensor.solcast_pv_forecast_forecast_today")
        self.assertEqual(selected[const.CONF_SOLCAST_TOMORROW],
                         "sensor.solcast_pv_forecast_forecast_tomorrow")

    def test_short_setup_skips_existing_sources(self):
        states = [
            FakeState("sensor.deye_pv_power", "W"),
            FakeState("sensor.deye_load_power", "W"),
            FakeState("sensor.moc_ladowarki_poprawna", "W"),
            FakeState("sensor.shellyem3_08f9e051e0b0_channel_b_power", "W"),
            FakeState("sensor.deye_battery", "%"),
            FakeState("sensor.temperatura_zewnetrzna", "°C"),
            FakeState("sensor.solcast_forecast_today", "kWh", detailedForecast=[]),
            FakeState("sensor.solcast_forecast_tomorrow", "kWh", detailedForecast=[]),
        ]
        detected = detect_entities(states)
        self.assertEqual(missing_required_sources(detected), ())
        self.assertEqual(detected[const.CONF_BATTERY_SOC], "sensor.deye_battery")
        self.assertEqual(detected[const.CONF_EV_POWER], "sensor.moc_ladowarki_poprawna")

    def test_short_setup_only_asks_missing_mandatory_entities(self):
        detected = detect_entities([
            FakeState("sensor.deye_pv_power", "W"),
            FakeState("sensor.deye_load_power", "W"),
            FakeState("sensor.moc_ladowarki_poprawna", "W"),
            FakeState("sensor.shellyem3_08f9e051e0b0_channel_b_power", "W"),
            FakeState("sensor.deye_battery", "%"),
        ])
        self.assertEqual(missing_required_sources(detected), (
            const.CONF_SOLCAST_TODAY,
            const.CONF_SOLCAST_TOMORROW,
            const.CONF_OUTDOOR_TEMP,
        ))

    def test_ambiguous_solcast_does_not_choose_wrong_plant(self):
        selected = detect_entities([
            FakeState("sensor.solcast_roof1_today", "kWh", detailedForecast=[]),
            FakeState("sensor.solcast_roof2_today", "kWh", detailedForecast=[]),
        ])
        self.assertNotIn(const.CONF_SOLCAST_TODAY, selected)


if __name__ == "__main__":
    unittest.main()
