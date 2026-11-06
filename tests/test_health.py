"""Offline tests: status history, stalled refresh, crash recovery and bounded log."""
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest

TARGET = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/health.py"
spec = importlib.util.spec_from_file_location("estadi_health_tests", TARGET)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)


class HealthTests(unittest.TestCase):
    def test_heartbeat_does_not_equal_working_forecast(self):
        h = mod.HealthJournal()
        h.attempt(NOW)
        h.finish(NOW + timedelta(seconds=2), "warning", "Brak prognozy")
        view = h.view(NOW + timedelta(minutes=2))
        self.assertEqual(view["status"], "warning")
        self.assertEqual(view["refresh_count"], 1)
        self.assertIsNone(view["last_success"])

    def test_success_and_stale_after_35_minutes(self):
        h = mod.HealthJournal()
        h.attempt(NOW)
        h.finish(NOW, "ok", "Plan gotowy", 100)
        self.assertEqual(h.view(NOW + timedelta(minutes=20))["status"], "ok")
        self.assertEqual(h.view(NOW + timedelta(minutes=36))["status"], "brak_odswiezania")
        self.assertEqual(h.view(NOW + timedelta(minutes=36))["last_success"], NOW.isoformat())

    def test_error_keeps_last_good_plan(self):
        h = mod.HealthJournal()
        h.attempt(NOW)
        h.finish(NOW, "ok", "Plan gotowy")
        h.attempt(NOW + timedelta(minutes=15))
        h.finish(NOW + timedelta(minutes=15), "error", "Awaria Forecast.Solar")
        self.assertEqual(h.view(NOW + timedelta(minutes=16))["status"], "error")
        self.assertEqual(h.fail_count, 1)
        self.assertEqual(h.last_success, NOW.isoformat())

    def test_persist_and_change_only_logging(self):
        h = mod.HealthJournal()
        for i in range(10):
            dt = NOW + timedelta(minutes=i)
            h.attempt(dt)
            h.finish(dt, "warning", "Brak SOC")
        self.assertEqual(len(h.events), 1)
        restored = mod.HealthJournal(h.export())
        self.assertEqual(restored.run_count, 10)
        self.assertEqual(restored.last_reason, "Brak SOC")

    def test_log_bounded_100(self):
        h = mod.HealthJournal()
        for i in range(220):
            h.add("warning", "TEST", f"message-{i}", NOW)
        self.assertEqual(len(h.export()["events"]), 100)
        self.assertEqual(len(h.view(NOW)["events"]), 20)

    def test_missing_and_invalid_old_dates_safe(self):
        h = mod.HealthJournal({"last_completed": "invalid", "events": []})
        self.assertEqual(h.view(NOW)["status"], "brak_odswiezania")
        self.assertIsNone(h.view(NOW)["age_seconds"])

    def test_timestamps_utc(self):
        h = mod.HealthJournal()
        shifted = NOW.astimezone(timezone(timedelta(hours=1)))
        h.attempt(shifted)
        h.finish(shifted, "ok", "Gotowe")
        self.assertEqual(h.last_completed, NOW.isoformat())


if __name__ == "__main__":
    unittest.main()
