"""Offline tests for the persisted, freeze-once hourly history."""
import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot"
package = types.ModuleType("estadi_test")
package.__path__ = [str(ROOT)]
sys.modules["estadi_test"] = package
for name in ("engine", "history"):
    spec = importlib.util.spec_from_file_location(f"estadi_test.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
engine = sys.modules["estadi_test.engine"]
history = sys.modules["estadi_test.history"]


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tz = timezone(timedelta(hours=1))
        self.now = datetime(2026, 11, 6, 21, 15, tzinfo=self.tz)

    def test_quarter_hour_ev_energy(self):
        book = history.HistoryBook()
        book.sample(self.now, pv=5000, home=8000, heat_pump=1000, ev=6900)
        book.sample(self.now + timedelta(minutes=15), pv=5000, home=8000, heat_pump=1000, ev=6900)
        self.assertAlmostEqual(book.summary('2026-11-06', today='2026-11-06')['ev_kwh'], 1.725)
        self.assertAlmostEqual(book.summary('2026-11-06', today='2026-11-06')['home_kwh'], 2.0)
        self.assertAlmostEqual(book.summary('2026-11-06', today='2026-11-06')['pv_kwh'], 1.25)

    def test_restart_long_gap_does_not_invent_energy(self):
        book = history.HistoryBook()
        book.sample(self.now, pv=6000)
        book.sample(self.now + timedelta(hours=2), pv=6000)
        self.assertIsNone(book.summary('2026-11-06', today='2026-11-06')['pv_kwh'])

    def test_missing_sensors_do_not_count_as_zero(self):
        book = history.HistoryBook()
        book.sample(self.now, pv=5000)
        book.sample(self.now + timedelta(minutes=15), pv=None)
        self.assertIsNone(book.summary('2026-11-06', today='2026-11-06')['pv_kwh'])

    def test_solar_forecast_freezes_and_persists(self):
        book = history.HistoryBook()
        tomorrow = (self.now + timedelta(days=1)).replace(hour=0, minute=0)
        slots = [engine.PvSlot(tomorrow + timedelta(minutes=30 * i), 1.0)
                 for i in range(48)]
        self.assertTrue(book.lock_forecast(self.now, slots))
        self.assertFalse(book.lock_forecast(self.now + timedelta(minutes=5),
                                            [engine.PvSlot(s.start, 100) for s in slots]))
        restored = history.HistoryBook(book.export())
        summary = restored.summary('2026-11-07', today='2026-11-08')
        self.assertEqual(summary['forecast_pv_kwh'], 24.0)
        self.assertEqual(len(restored.hourly_comparison('2026-11-07')), 24)
        self.assertEqual(summary['pv_error_kwh'], None)

    def test_short_forecast_does_not_lock(self):
        book = history.HistoryBook()
        tomorrow = self.now + timedelta(days=1)
        self.assertFalse(book.lock_forecast(self.now, [engine.PvSlot(tomorrow, 1)]))

    def test_accuracy_only_for_completed_days_with_coverage(self):
        book = history.HistoryBook()
        target = datetime(2026, 11, 7, 0, 0, tzinfo=self.tz)
        slots = [engine.PvSlot(target + timedelta(minutes=30 * i), 2.0)
                 for i in range(48)]
        book.lock_forecast(self.now, slots)
        for i in range(97):
            book.sample(target + timedelta(minutes=15 * i), pv=2000)
        summary = book.summary('2026-11-07', today='2026-11-08')
        self.assertEqual(summary['pv_coverage_pct'], 100)
        self.assertTrue(summary['comparable'])
        self.assertAlmostEqual(summary['pv_kwh'], 48.0, places=2)
        self.assertAlmostEqual(summary['pv_error_kwh'], 0, places=2)
        self.assertFalse(book.summary('2026-11-07', today='2026-11-07')['comparable'])


if __name__ == '__main__':
    unittest.main()
