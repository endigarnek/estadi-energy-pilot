"""Regression tests for 7–30 day learned demand and EV topology."""
import importlib.util
from pathlib import Path
from datetime import date, timedelta
import unittest

TARGET = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/house_learning.py"
spec = importlib.util.spec_from_file_location("estadi_house_learning_test", TARGET)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def day_row(home=1.0, ev=0.0, coverage=1.0):
    def hours(value):
        return {f"{h:02}:00": value for h in range(24)}
    return {"actual": {"home": hours(home), "ev": hours(ev)},
            "coverage": {"home": hours(coverage), "ev": hours(coverage)}}


class HouseLearningTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 20)
        self.days = {(self.today - timedelta(days=i)).isoformat(): day_row()
                     for i in range(1, 15)}

    def test_requires_seven_complete_days_and_topology(self):
        result = mod.build_house_profile(self.days, self.today)
        self.assertEqual(result["state"], "niepotwierdzona_topologia_ev")
        result = mod.build_house_profile(self.days, self.today, ev_in_home_load=False)
        self.assertEqual(result["state"], "gotowy")
        self.assertEqual(result["complete_days"], 14)

    def test_missing_and_partial_days_not_zero(self):
        days = dict(list(self.days.items())[:6])
        days[(self.today - timedelta(days=7)).isoformat()] = day_row(coverage=0.4)
        result = mod.build_house_profile(days, self.today, ev_in_home_load=False)
        self.assertEqual(result["state"], "ucze_sie")
        self.assertEqual(result["complete_days"], 6)

    def test_ev_removed_only_when_included_in_home(self):
        days = {key: day_row(home=5.0, ev=3.0) for key in self.days}
        included = mod.build_house_profile(days, self.today, ev_in_home_load=True)
        excluded = mod.build_house_profile(days, self.today, ev_in_home_load=False)
        self.assertEqual(included["profiles"]["weekday"][0]["p50_kwh"], 2.0)
        self.assertEqual(excluded["profiles"]["weekday"][0]["p50_kwh"], 5.0)

    def test_missing_ev_data_blocks_day_if_included(self):
        days = {key: {"actual": {"home": {f"{h:02}:00": 2.0 for h in range(24)}},
                      "coverage": {"home": {f"{h:02}:00": 1.0 for h in range(24)}}}
                for key in self.days}
        result = mod.build_house_profile(days, self.today, ev_in_home_load=True)
        self.assertEqual(result["complete_days"], 0)

    def test_p90_captures_rare_kitchen_spike(self):
        days = {key: day_row(home=0.4) for key in self.days}
        for key in sorted(days)[-3:]:
            days[key]["actual"]["home"]["18:00"] = 3.0
        result = mod.build_house_profile(days, self.today, ev_in_home_load=False)
        evening = result["profiles"]["weekday"][18]
        self.assertGreaterEqual(evening["p90_kwh"], evening["p50_kwh"])

    def test_no_future_data_and_historical_limit(self):
        self.days[(self.today + timedelta(days=1)).isoformat()] = day_row(100)
        self.days[(self.today - timedelta(days=40)).isoformat()] = day_row(100)
        result = mod.build_house_profile(self.days, self.today, ev_in_home_load=False)
        self.assertEqual(result["complete_days"], 14)


if __name__ == "__main__":
    unittest.main()
