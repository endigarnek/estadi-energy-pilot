"""Test 48h sequential SOC simulation without installing Home Assistant."""
import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PACKAGE = "pilot_simulation_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


battery = load_module("battery_model")
engine = load_module("engine")
tariffs = load_module("tariffs")
simulation = load_module("simulation_48h")


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 12, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
        self.model = battery.BatteryModel(nominal_kwh=28, minimum_soc=10, maximum_soc=100)
        self.slots = [
            engine.PvSlot(self.now.astimezone(timezone.utc) + timedelta(hours=i), 0.0, 60)
            for i in range(48)
        ]
        self.learning = {"baseline_ready": False, "base_profiles": {}}

    def run_sim(self, *, now=None, slots=None, soc=60, base=500, ev=None, **kwargs):
        return simulation.simulate_48h(
            now or self.now, self.slots if slots is None else slots, [],
            self.learning, self.model, soc, 10,
            tariff="G12w", baseload_w=base, mild_w=600, cold_w=1200,
            pv_discount_pct=0, efficiency_pct=90,
            battery_max_kw=10, grid_limit_kw=15, ev_now_kw=ev,
            **kwargs,
        )

    def test_48h_never_discharge_below_soc_floor(self):
        result = self.run_sim(soc=60)
        self.assertEqual(result["status"], "gotowa")
        self.assertEqual(result["forecast_hours"], 48)
        self.assertEqual(len(result["timeline_hours"]), 48)
        self.assertGreater(result["grid_import_kwh"], 0)
        self.assertGreaterEqual(result["soc_min_pct"], 10)
        self.assertAlmostEqual(result["soc_end_pct"], 10, places=1)
        self.assertEqual(result["scenario"], "bez_dodatkowego_ladowania_z_sieci")

    def test_full_reserve_does_not_invent_battery_energy(self):
        result = self.run_sim(soc=10)
        self.assertEqual(result["soc_end_pct"], 10)
        self.assertAlmostEqual(result["grid_import_kwh"], 24, places=2)
        self.assertAlmostEqual(result["without_battery_import_kwh"], 24, places=2)

    def test_current_ev_only_in_first_quarter_not_future_day(self):
        result = self.run_sim(soc=10, ev=6.9)
        self.assertAlmostEqual(result["ev_kwh"], 1.725, places=2)
        self.assertTrue(result["future_ev_sessions_unknown"])
        self.assertGreater(result["house_kwh"], 24)

    def test_forecast_lacks_daylight_hour_fails_closed(self):
        slots = self.slots[:5]
        result = self.run_sim(slots=slots)
        self.assertEqual(result["status"], "niepelna_prognoza_pv")
        self.assertLess(result["forecast_hours"], 48)
        self.assertNotEqual(result["quality"], "pelna")
        self.assertTrue(result["reason"].startswith("Brak godzinowej prognozy"))

    def test_no_prices_no_fictitious_savings(self):
        result = self.run_sim(soc=10)
        self.assertIsNone(result["cost_import_pln"])
        self.assertIsNone(result["savings_pln"])

    def test_price_does_not_pretend_to_include_export_credit(self):
        result = self.run_sim(soc=10, prices={"cheap": 0.5, "peak": 1.0})
        self.assertGreater(result["cost_import_pln"], 0)
        self.assertIsNone(result["savings_pln"])

    def test_future_solar_cannot_offset_morning_shortfall(self):
        slots = []
        for i in range(48):
            at = self.now.astimezone(timezone.utc) + timedelta(hours=i)
            solar = 8.0 if 10 <= i < 13 else 0.0
            slots.append(engine.PvSlot(at, solar, 60))
        result = self.run_sim(slots=slots, soc=10, base=1000)
        self.assertGreaterEqual(result["grid_import_kwh"], 4.0)
        self.assertGreater(result["pv_battery_kwh"], 0)

    def test_timezone_dst_is_48_elapsed_hours(self):
        now = datetime(2026, 10, 24, 23, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
        utc = now.astimezone(timezone.utc)
        slots = [engine.PvSlot(utc + timedelta(hours=i), 0.0, 60) for i in range(48)]
        result = self.run_sim(now=now, slots=slots, soc=10)
        self.assertEqual(result["forecast_hours"], 48)
        self.assertEqual(len(result["timeline_hours"]), 48)

    def test_pump_temperature_is_counted_once(self):
        result = self.run_sim(soc=10, base=0, now=self.now.replace(month=12))
        # Current temperature 10°C: the simplified heat pump model is off.
        self.assertAlmostEqual(result["house_kwh"], 0, places=2)
        self.assertAlmostEqual(result["pump_kwh"], 0, places=2)


if __name__ == "__main__":
    unittest.main()
