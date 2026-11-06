"""Pure tests: fixed-in-time forecasts versus later measured SOC and PV."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

SRC = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/forecast_accuracy.py"
spec = importlib.util.spec_from_file_location("forecast_accuracy_test", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TZ = ZoneInfo("Europe/Warsaw")
START = datetime(2026, 11, 6, 13, 0, tzinfo=TZ)


def sim():
    return {
        "status": "gotowa", "quality": "wstepna",
        "timeline_hours": [{"soc_do": round(80 - h * 1.25, 1)}
                           for h in range(1, 49)]
    }


def plan(start=START):
    return {"status": "wstepny_plan", "target_soc": 60,
            "power_kw": 5,
            "start": (start + timedelta(minutes=15)).isoformat(),
            "end_window": (start + timedelta(hours=2)).isoformat()}


class AccuracyTests(unittest.TestCase):
    def test_snapshot_four_fixed_horizons_and_a_plan_goal(self):
        audit = mod.AccuracyJournal()
        self.assertTrue(audit.capture(START, sim(), plan(), nominal_kwh=28))
        self.assertEqual(len(audit.checkpoints), 5)
        self.assertEqual([x["horizon_h"] for x in audit.checkpoints[:4]], [3, 6, 12, 24])
        self.assertEqual(audit.checkpoints[0]["predicted_soc_pct"], 76.2)
        self.assertEqual(audit.checkpoints[0]["status"], "pending")
        self.assertFalse(audit.capture(START + timedelta(minutes=15), sim(), plan()))
        self.assertEqual(len(audit.checkpoints), 5)

    def test_only_new_measurement_after_target_can_score_forecast(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, sim(), None)
        self.assertFalse(audit.observe(START + timedelta(hours=2), 66))
        self.assertTrue(audit.observe(START + timedelta(hours=3, minutes=5), 73))
        entry = audit.checkpoints[0]
        self.assertEqual(entry["status"], "zaobserwowano")
        self.assertEqual(entry["deviation_pp"], -3.2)
        self.assertFalse(audit.observe(START + timedelta(hours=3, minutes=20), 12))
        self.assertEqual(entry["observed_soc_pct"], 73)
        self.assertEqual(audit.report()["horyzonty_soc"]["3"]["porownania"], 1)

    def test_expired_measurement_does_not_invent_soc(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, sim(), None)
        self.assertTrue(audit.observe(START + timedelta(hours=4), None))
        self.assertEqual(audit.checkpoints[0]["status"], "brak_odczytu")
        self.assertEqual(audit.report()["brak_odczytu_w_terminie"], 1)

    def test_goal_observed_but_never_claims_execution(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, None, plan())
        self.assertTrue(audit.observe(START + timedelta(hours=2, minutes=6), 61))
        report = audit.report()
        self.assertEqual(report["obserwacje_celu"]["cel_osiagniety"], 1)
        self.assertFalse(report["automatyzacja_wlaczona"])
        self.assertIsNone(report["oszczednosci_pln"])
        self.assertIn("nie oznacza", report["uwaga"])

    def test_goal_not_reached_is_not_automatic_failure_claim(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, None, plan())
        audit.observe(START + timedelta(hours=2), 45)
        report = audit.report()
        self.assertEqual(report["obserwacje_celu"]["cel_nieosiagniety"], 1)
        self.assertFalse(report["automatyzacja_wlaczona"])

    def test_incomplete_simulation_does_not_snapshot(self):
        audit = mod.AccuracyJournal()
        self.assertFalse(audit.capture(START, {"status": "niepelna_prognoza_pv",
                                               "timeline_hours": sim()["timeline_hours"]}, None))
        self.assertEqual(len(audit.checkpoints), 0)

    def test_snapshot_6h_interval_and_persistence(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, sim(), None)
        self.assertFalse(audit.capture(START + timedelta(hours=5), sim(), None))
        self.assertTrue(audit.capture(START + timedelta(hours=6), sim(), None))
        restored = mod.AccuracyJournal(audit.export())
        self.assertEqual(len(restored.checkpoints), 8)
        self.assertFalse(restored.capture(START + timedelta(hours=7), sim(), None))

    def test_pv_metrics_only_on_real_complete_past_days(self):
        data = [
            {"date": "2026-11-04", "comparable": True, "pv_kwh": 10,
             "forecast_pv_kwh": 12},
            {"date": "2026-11-05", "comparable": True, "pv_kwh": 5,
             "forecast_pv_kwh": 4},
            {"date": "2026-11-06", "comparable": False, "pv_kwh": 50,
             "forecast_pv_kwh": 0},
        ]
        report = mod.pv_verification(data)
        self.assertEqual(report["dni"], 2)
        self.assertEqual(report["sredni_blad_bezwzgledny_kwh"], 1.5)
        self.assertEqual(report["wape_pct"], 20.0)
        self.assertEqual(report["bias_kwh"], .5)

    def test_invalid_soc_does_not_count_as_real(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, sim(), None)
        self.assertFalse(audit.observe(START + timedelta(hours=3), None))
        self.assertIsNone(mod.valid_soc(True))
        self.assertIsNone(mod.valid_soc("unavailable"))
        self.assertEqual(audit.report()["horyzonty_soc"]["3"]["porownania"], 0)

    def test_timezone_and_dst_targets_use_real_elapsed_hours(self):
        start = datetime(2026, 10, 24, 23, tzinfo=TZ)
        audit = mod.AccuracyJournal()
        audit.capture(start, sim(), None)
        due = mod.parse_instant(audit.checkpoints[0]["due_at"])
        self.assertEqual((due - start.astimezone(timezone.utc)).total_seconds(), 10800)

    def test_no_duplicate_after_restart_with_plan_goal(self):
        audit = mod.AccuracyJournal()
        audit.capture(START, sim(), plan())
        restored = mod.AccuracyJournal(audit.export())
        self.assertFalse(restored.capture(START + timedelta(minutes=5), sim(), plan()))
        self.assertEqual(len(restored.checkpoints), 5)


if __name__ == "__main__":
    unittest.main()
