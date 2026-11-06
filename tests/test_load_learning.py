import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot"
package = types.ModuleType("learning_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
for name in ("tariffs", "load_learning"):
    spec = importlib.util.spec_from_file_location(f"learning_test.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
learning = sys.modules["learning_test.load_learning"]


def make_history(days=10, ev_at=None, home_at=None):
    rows = {}
    for day in range(1, days + 1):
        hourly_home = {f"{i:02}:00": 0.5 for i in range(24)}
        hourly_ev = {f"{i:02}:00": 0.0 for i in range(24)}
        if ev_at is not None:
            hourly_ev[f"{ev_at:02}:00"] = 6.9
            hourly_home[f"{ev_at:02}:00"] = 7.4
        if home_at is not None:
            hourly_home[f"{home_at:02}:00"] = 2.5
        rows[f"2026-10-{day:02}"] = {
            "actual": {"home": hourly_home, "ev": hourly_ev},
            "coverage": {
                "home": {f"{i:02}:00": 1.0 for i in range(24)},
                "ev": {f"{i:02}:00": 1.0 for i in range(24)},
            },
        }
    return rows


class LearningTests(unittest.TestCase):
    def test_need_seven_complete_days(self):
        profile = learning.build_household_profile(make_history(3), date(2026, 11, 1))
        self.assertEqual(profile["status"], "uczy_sie")
        self.assertEqual(profile["days_complete"], 3)

    def test_ev_spikes_are_not_learned_as_home(self):
        profile = learning.build_household_profile(make_history(10, ev_at=23), date(2026, 11, 1))
        self.assertEqual(profile["days_complete"], 10)
        self.assertEqual(profile["ev_hours_excluded"], 10)
        self.assertTrue(all(v["p50_kwh"] < 1 for k, v in profile["hourly"].items()))

    def test_appliances_increase_p90_without_electric_car(self):
        profile = learning.build_household_profile(make_history(10, home_at=18), date(2026, 11, 1))
        self.assertEqual(profile["status"], "gotowy")
        self.assertEqual(profile["hourly"]["weekday_18"]["p50_kwh"], 2.5)

    def test_missing_ev_coverage_refuses_to_learn(self):
        rows = make_history(10)
        for row in rows.values():
            row["coverage"]["ev"] = {}
        profile = learning.build_household_profile(rows, date(2026, 11, 1))
        self.assertEqual(profile["status"], "uczy_sie")
        self.assertEqual(profile["days_complete"], 0)

    def test_24_hour_projection_requires_complete_bins(self):
        profile = learning.build_household_profile(make_history(10), date(2026, 11, 1))
        result = learning.next_24h_profile(profile, datetime(2026, 11, 6, 10, tzinfo=ZoneInfo("Europe/Warsaw")))
        self.assertTrue(result["available"])
        self.assertEqual(result["total_p50_kwh"], 12.0)

    def test_missing_history_never_makes_up_zero(self):
        result = learning.next_24h_profile(learning.build_household_profile({}, date(2026, 11, 1)),
                                           datetime(2026, 11, 6, 10, tzinfo=ZoneInfo("Europe/Warsaw")))
        self.assertFalse(result["available"])
        self.assertIsNone(result["total_p50_kwh"])


if __name__ == "__main__":
    unittest.main()
