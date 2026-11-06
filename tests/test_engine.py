import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

ENGINE = pathlib.Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/engine.py"
spec = importlib.util.spec_from_file_location("pilot_engine", ENGINE)
engine = importlib.util.module_from_spec(spec)
sys.modules["pilot_engine"] = engine
spec.loader.exec_module(engine)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tz = timezone(timedelta(hours=1))
        self.today = datetime(2026, 11, 6, 22, 0, tzinfo=self.tz)
        self.slots = []
        for day in (6, 7, 8):
            start = datetime(2026, 11, day, tzinfo=self.tz)
            self.slots.extend(engine.PvSlot(start + timedelta(minutes=30 * i),
                                             1.0 if 7 <= (i * 0.5) < 16 else 0.0)
                              for i in range(48))

    def test_pump_interpolation(self):
        self.assertEqual(engine.pump_power_w(8), 0)
        self.assertEqual(engine.pump_power_w(7.9), 604.6153846153846)
        self.assertEqual(engine.pump_power_w(-5), 1200)
        self.assertEqual(engine.pump_power_w(-15), 1200)
        self.assertAlmostEqual(engine.pump_power_w(0), 969.23, 2)

    def test_windows_after_night_start(self):
        night, afternoon = engine.upcoming_windows(self.today)
        self.assertEqual((night[0].day, night[0].hour, night[1].hour), (7, 7, 13))
        self.assertEqual((afternoon[0].day, afternoon[0].hour), (7, 16))

    def test_window_before_night_end(self):
        now = datetime(2026, 11, 7, 5, tzinfo=self.tz)
        night, _ = engine.upcoming_windows(now)
        self.assertEqual(night[0].day, 7)

    def test_energy_half_hour_conversion(self):
        a = {"detailedForecast": [{"period_start": slot.start.isoformat(),
                                   "pv_estimate": slot.power_kw} for slot in self.slots]}
        parsed = engine.parse_pv_slots(a)
        plan = engine.plan_window("night", datetime(2026, 11, 7, 7, tzinfo=self.tz),
                                  datetime(2026, 11, 7, 13, tzinfo=self.tz),
                                  parsed, [], 15, 20, 400, 20, 95, 0, 90, 1, 600, 1200)
        self.assertEqual(plan.pv_kwh, 6.0)
        self.assertEqual(plan.load_kwh, 2.4)
        self.assertEqual(plan.grid_gap_kwh, 0)
        self.assertEqual(plan.target_soc, 25)

    def test_cloudy_freezing_day(self):
        pv = [engine.PvSlot(s.start, 0) for s in self.slots]
        plan = engine.plan_window("night", datetime(2026, 11, 7, 7, tzinfo=self.tz),
                                  datetime(2026, 11, 7, 13, tzinfo=self.tz),
                                  pv, [], -5, 20, 400, 20, 95, 15, 90, 1, 600, 1200)
        self.assertEqual(plan.load_kwh, 9.6)
        self.assertEqual(plan.heat_kwh, 7.2)
        self.assertEqual(plan.target_soc, 79)

    def test_fail_closed_without_solar_forecast(self):
        plan = engine.plan_window("night", datetime(2026, 11, 7, 7, tzinfo=self.tz),
                                  datetime(2026, 11, 7, 13, tzinfo=self.tz),
                                  [], [], -5, 20, 400, 20, 95, 15, 90, 1, 600, 1200)
        self.assertFalse(plan.can_calculate)

    def test_charge_recommendation_only_in_cheap_window(self):
        attrs = {"detailedForecast": [{"period_start": s.start.isoformat(),
                                       "pv_estimate": s.power_kw} for s in self.slots]}
        night = engine.get_all_plans(self.today, [attrs], [], -5, 25, 20)
        self.assertEqual(night["charge_window"], "night")
        self.assertTrue(night["recommended"])
        midday = engine.get_all_plans(self.today.replace(hour=14), [attrs], [], -5, 25, 20)
        self.assertEqual(midday["charge_window"], "afternoon")
        expensive = engine.get_all_plans(self.today.replace(hour=19), [attrs], [], -5, 25, 20)
        self.assertIsNone(expensive["charge_window"])
        self.assertFalse(expensive["recommended"])

    def test_forecast_weather(self):
        temps = engine.parse_weather_slots([{"datetime": "2026-11-07T07:00:00+01:00", "temperature": -5}])
        self.assertEqual(engine._temperature_at(datetime(2026, 11, 7, 9, tzinfo=self.tz), temps, 10), -5)


if __name__ == "__main__":
    unittest.main()
