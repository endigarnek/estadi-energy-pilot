"""Regression tests for the 0.3 tariff, battery and grid advice."""
import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot"
package = types.ModuleType("p0_ep20")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
for name in ("tariffs", "battery_model", "grid_guard", "charge_planner"):
    spec = importlib.util.spec_from_file_location(f"{package.__name__}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
tariffs = sys.modules["p0_ep20.tariffs"]
battery = sys.modules["p0_ep20.battery_model"]
grid = sys.modules["p0_ep20.grid_guard"]
planner = sys.modules["p0_ep20.charge_planner"]
TZ = ZoneInfo("Europe/Warsaw")


class TariffTests(unittest.TestCase):
    def at(self, y=2026, m=11, d=6, h=14, minute=0):
        return datetime(y, m, d, h, minute, tzinfo=TZ)

    def test_g12w_cheap_middle_only_13_to_15(self):
        self.assertEqual(tariffs.tariff_zone(self.at(h=14), "G12w"), "cheap")
        self.assertEqual(tariffs.tariff_zone(self.at(h=15), "G12w"), "peak")
        self.assertEqual(tariffs.tariff_zone(self.at(h=16), "G12w"), "peak")
        self.assertEqual(tariffs.tariff_zone(self.at(h=22), "G12w"), "cheap")
        self.assertEqual(tariffs.tariff_zone(self.at(h=6), "G12w"), "peak")

    def test_weekend_and_statutory_holiday(self):
        self.assertEqual(tariffs.tariff_zone(self.at(d=7, h=10), "G12w"), "cheap")
        self.assertEqual(tariffs.tariff_zone(self.at(d=11, h=10), "G13"), "cheap")
        self.assertIn(date(2026, 12, 24), tariffs.poland_public_holidays(2026))
        self.assertEqual(tariffs.easter_sunday(2026), date(2026, 4, 5))

    def test_g13_winter_summer(self):
        self.assertEqual(tariffs.tariff_zone(self.at(h=16), "G13"), "evening")
        self.assertEqual(tariffs.tariff_zone(self.at(h=14), "G13"), "cheap")
        self.assertEqual(tariffs.tariff_zone(self.at(m=7, d=6, h=18), "G13"), "cheap")
        self.assertEqual(tariffs.tariff_zone(self.at(m=7, d=6, h=20), "G13"), "evening")

    def test_window_ends_at_15_on_friday(self):
        start, end = tariffs.next_cheap_window(self.at(h=12, minute=5), "G12w")
        self.assertEqual((start.hour, end.hour), (13, 15))

    def test_prices_no_invented_rates(self):
        self.assertIsNone(tariffs.zone_prices("G12w", None, None))
        self.assertIsNone(tariffs.zone_prices("G13", 0.5, 1.2))
        self.assertEqual(tariffs.zone_prices("G13", 0.5, 1.2, 2.0)["evening"], 2.0)


class BatteryTests(unittest.TestCase):
    def test_28_nominal_soc_10_to_100(self):
        b = battery.BatteryModel()
        self.assertAlmostEqual(b.window_energy_kwh, 25.2)
        self.assertAlmostEqual(b.energy_to_target_kwh(40, 80), 11.2)

    def test_usable_after_soh_and_upgrade(self):
        self.assertAlmostEqual(battery.BatteryModel(42).window_energy_kwh, 37.8)
        self.assertAlmostEqual(battery.BatteryModel(28, 80).window_energy_kwh, 20.16)

    def test_correction(self):
        self.assertEqual(battery.BatteryModel(correction_pp=8).adjusted_target(45), 53)
        self.assertEqual(battery.BatteryModel(correction_pp=15).adjusted_target(90), 100)


class GridGuardTests(unittest.TestCase):
    def test_ev11_pump2_home1_zero_for_battery(self):
        g = grid.calculate_grid_guard(14000, 0, import_sign=1)
        self.assertEqual(g.allowed_charge_kw, 0)
        self.assertEqual(g.import_kw, 14.0)
        self.assertFalse(g.automatic_ready)

    def test_ev_stops_restore_10kw(self):
        g = grid.calculate_grid_guard(3000, 0, import_sign=1)
        self.assertEqual(g.allowed_charge_kw, 10)

    def test_current_grid_already_includes_charge(self):
        g = grid.calculate_grid_guard(12000, 3000, import_sign=1)
        self.assertEqual(g.allowed_charge_kw, 4.0)

    def test_no_sign_is_not_valid(self):
        g = grid.calculate_grid_guard(12000, 3000, import_sign=0)
        self.assertIsNone(g.allowed_charge_kw)
        self.assertEqual(g.state, "blokada")

    def test_phase_overload_limits_cap(self):
        g = grid.calculate_grid_guard(
            9000, 1000, import_sign=1,
            phase_currents_a=(35, 8, 8), phase_limits_a=(32, 32, 32),
            phase_voltages_v=(230, 230, 230))
        self.assertEqual(g.allowed_charge_kw, 1.0)
        self.assertTrue(g.phase_checked)


class PlannerTests(unittest.TestCase):
    def test_g12w_requires_more_power_than_preferred_5kw(self):
        start = datetime(2026, 11, 6, 13, tzinfo=TZ)
        end = datetime(2026, 11, 6, 15, tzinfo=TZ)
        p = planner.propose(start, (start, end), 40, 80, battery.BatteryModel(), 10)
        self.assertEqual(p.state, "wstepny")
        self.assertGreaterEqual(p.power_kw, 7)
        self.assertLessEqual(datetime.fromisoformat(p.finish), end - timedelta(minutes=15))

    def test_no_unverified_grid_power(self):
        now = datetime(2026, 11, 6, 13, tzinfo=TZ)
        p = planner.propose(now, (now, now + timedelta(hours=2)), 40, 80,
                            battery.BatteryModel(), None)
        self.assertEqual(p.state, "brak_pomiaru")

    def test_insufficient_time_and_ev(self):
        now = datetime(2026, 11, 6, 14, tzinfo=TZ)
        p = planner.propose(now, (now, now + timedelta(hours=1)), 40, 80,
                            battery.BatteryModel(), 4)
        self.assertEqual(p.state, "nieosiagalny")


if __name__ == "__main__":
    unittest.main()
