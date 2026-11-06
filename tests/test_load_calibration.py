"""Regression tests of leakage-free home calibration and EV history quality."""
import importlib.util
from datetime import date, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
spec = importlib.util.spec_from_file_location("load_calibration_tests", ROOT / "load_calibration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(day: date, *, baseline=1.2, pump=.35,
            ev_schedule=None, ev_coverage=True, home_coverage=True):
    """Deye home includes both pump and EV; energy is kWh per hour."""
    ev_schedule = ev_schedule or {}
    row = {"actual": {"home": {}, "ev": {}, "heat_pump": {}},
           "coverage": {"home": {}, "ev": {}, "heat_pump": {}}}
    for h in range(24):
        key = f"{h:02}:00"
        ev = float(ev_schedule.get(h, 0.))
        row["actual"]["home"][key] = baseline + pump + ev
        row["actual"]["ev"][key] = ev
        row["actual"]["heat_pump"][key] = pump
        for channel in ("home", "ev", "heat_pump"):
            coverage = 1.
            if channel == "ev" and not ev_coverage:
                coverage = 0.
            if channel == "home" and not home_coverage:
                coverage = 0.
            row["coverage"][channel][key] = coverage
    return row


class LoadCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 21)
        self.days = {}
        for offset in range(14, 0, -1):
            d = self.today - timedelta(days=offset)
            schedule = ({18: 6.5, 19: 6.5} if offset % 2 == 0 else {})
            self.days[d.isoformat()] = fixture(d, ev_schedule=schedule)

    def test_subtract_ev_and_pump_exactly_once(self):
        result = module.analyze_load_history(self.days, self.today)
        self.assertEqual(result["status"], "oceniono")
        self.assertEqual(result["base_median_w"], 1200)
        self.assertEqual(result["mae_kwh_hour"], 0)
        self.assertEqual(result["bias_actual_minus_forecast_kwh_hour"], 0)
        self.assertTrue(result["home_includes_ev_and_heat_pump"])
        self.assertFalse(result["auto_calibration_enabled"])

    def test_leave_one_day_out_detects_unexpected_new_base_load(self):
        key = (self.today - timedelta(days=1)).isoformat()
        self.days[key] = fixture(self.today - timedelta(days=1), baseline=2.8)
        result = module.analyze_load_history(self.days, self.today)
        self.assertEqual(result["status"], "oceniono")
        self.assertGreater(result["mae_kwh_hour"], 0)
        self.assertGreater(result["bias_actual_minus_forecast_kwh_hour"], 0)

    def test_missing_ev_coverage_does_not_become_zero_consumption(self):
        bad = {key: fixture(date.fromisoformat(key), ev_coverage=False)
               for key in self.days}
        model = module.analyze_load_history(bad, self.today)
        self.assertEqual(model["complete_days"], 0)
        self.assertEqual(model["status"], "zbieranie_danych")
        self.assertIsNone(model["base_median_w"])
        risk = module.analyze_ev_history(bad, self.today)
        self.assertFalse(risk["risk_ready"])

    def test_inconsistent_power_ev_exceeds_dye_load_rejected(self):
        key = (self.today - timedelta(days=1)).isoformat()
        row = fixture(date.fromisoformat(key))
        row["actual"]["ev"]["18:00"] = 100.
        self.days[key] = row
        output = module.analyze_load_history(self.days, self.today)
        self.assertEqual(output["complete_days"], 14)
        self.assertGreaterEqual(output["tested_hours"], 72)
        # P50 should not be corrupted by 100 kWh fictitious EV.
        self.assertEqual(output["base_median_w"], 1200)

    def test_ev_stress_requires_weekdays_and_weekends_at_least_3(self):
        result = module.analyze_ev_history(self.days, self.today)
        self.assertTrue(result["risk_ready"])
        self.assertEqual(result["complete_days"], 14)
        self.assertEqual(len(result["profiles"]["weekday"]["p90_kwh_per_hour"]), 24)
        self.assertGreater(result["profiles"]["weekday"]["peak_hour_kwh"], 0)
        self.assertFalse(result["future_sessions_known"])

    def test_ev_stress_does_not_guess_if_weekend_missing(self):
        only_weekday = {key: row for key, row in self.days.items()
                        if date.fromisoformat(key).weekday() < 5}
        output = module.analyze_ev_history(only_weekday, self.today)
        self.assertFalse(output["risk_ready"])
        self.assertEqual(output["profiles"], {})

    def test_ev_zero_is_valid_only_with_coverage(self):
        ev_free = {key: fixture(date.fromisoformat(key)) for key in self.days}
        output = module.analyze_ev_history(ev_free, self.today)
        self.assertTrue(output["risk_ready"])
        self.assertEqual(output["profiles"]["weekend"]["peak_hour_kwh"], 0)
        self.assertEqual(output["profiles"]["weekday"]["hours_with_risk"], 0)

    def test_future_or_current_day_is_not_training(self):
        future = fixture(self.today, baseline=20)
        days = {**self.days, self.today.isoformat(): future}
        score = module.analyze_load_history(days, self.today)
        self.assertEqual(score["base_median_w"], 1200)
        self.assertEqual(score["complete_days"], 14)

    def test_pv_bias_guidance_uses_locked_complete_days_only(self):
        rows = [{"comparable": True, "forecast_pv_kwh": 10, "pv_kwh": 8}
                for _ in range(7)]
        rows.append({"comparable": False, "forecast_pv_kwh": 50, "pv_kwh": 0})
        report = module.pv_bias_guidance(rows)
        self.assertEqual(report["complete_pv_days"], 7)
        self.assertEqual(report["suggested_total_pv_discount_pct"], 20)
        self.assertFalse(report["auto_apply"])

    def test_pv_no_recommendation_before_7_days(self):
        rows = [{"comparable": True, "forecast_pv_kwh": 10, "pv_kwh": 5}
                for _ in range(6)]
        report = module.pv_bias_guidance(rows)
        self.assertEqual(report["status"], "zbieranie_danych")
        self.assertIsNone(report["suggested_total_pv_discount_pct"])

    def test_near_zero_pv_forecasts_are_excluded(self):
        report = module.pv_bias_guidance([
            {"comparable": True, "forecast_pv_kwh": .01, "pv_kwh": 2}
            for _ in range(9)
        ])
        self.assertEqual(report["complete_pv_days"], 0)
        self.assertIsNone(report["historical_actual_forecast_ratio"])


if __name__ == "__main__":
    unittest.main()
