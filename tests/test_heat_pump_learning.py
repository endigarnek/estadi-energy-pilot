"""Offline regression tests for measured heat pump/temperature pairs and holdout."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PKG = "pilot_heat_pump_tests"
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


engine = load("engine")
tariffs = load("tariffs")
sim = load("simulation_48h")
history = load("history")
learning = load("heat_pump_learning")
TODAY = date(2026, 11, 23)
TZ = ZoneInfo("Europe/Warsaw")


def fixture(day: date, *, power_factor=1., missing_temp=False):
    record = {
        "actual": {"heat_pump": {}},
        "coverage": {"heat_pump": {}},
        "temperature_degree_hours": {},
        "temperature_coverage": {},
    }
    for hour in range(24):
        name = f"{hour:02}:00"
        temp, watts = (-7, 1800) if hour < 8 else (2, 1200) if hour < 16 else (8, 600)
        record["actual"]["heat_pump"][name] = watts * power_factor / 1000
        record["coverage"]["heat_pump"][name] = 1.
        if not missing_temp:
            record["temperature_degree_hours"][name] = float(temp)
            record["temperature_coverage"][name] = 1.
    return record


def days(count=14):
    return {(TODAY - timedelta(days=offset)).isoformat():
            fixture(TODAY - timedelta(days=offset))
            for offset in range(count, 0, -1)}


class PumpLearningTests(unittest.TestCase):
    def test_temperature_integrates_only_with_measured_pump_energy(self):
        book = history.HistoryBook()
        now = datetime(2026, 11, 23, 12, tzinfo=TZ)
        book.sample(now, heat_pump=1000, outdoor_temp=0)
        book.sample(now + timedelta(minutes=15), heat_pump=1000, outdoor_temp=4)
        record = book.days["2026-11-23"]
        self.assertAlmostEqual(record["actual"]["heat_pump"]["12:00"], .25)
        self.assertAlmostEqual(record["temperature_coverage"]["12:00"], .25)
        self.assertAlmostEqual(record["temperature_degree_hours"]["12:00"], .5)
        self.assertAlmostEqual(record["temperature_degree_hours"]["12:00"] /
                               record["temperature_coverage"]["12:00"], 2)

    def test_invalid_temperature_never_becomes_a_zero_celsius(self):
        book = history.HistoryBook()
        now = datetime(2026, 11, 23, 12, tzinfo=TZ)
        book.sample(now, heat_pump=1200, outdoor_temp=None)
        book.sample(now + timedelta(minutes=15), heat_pump=1200, outdoor_temp=0)
        record = book.days["2026-11-23"]
        self.assertNotIn("temperature_degree_hours", record)
        self.assertAlmostEqual(record["actual"]["heat_pump"]["12:00"], .3)

    def test_old_history_without_temperature_cannot_be_trained_retroactively(self):
        records = days()
        for item in records.values():
            item.pop("temperature_degree_hours")
            item.pop("temperature_coverage")
        result = learning.train_heat_pump(records, TODAY)
        self.assertEqual(result["status"], "zbieranie_temperatury_i_energii")
        self.assertEqual(result["valid_hours"], 0)
        self.assertFalse(result["automatic_use"])

    def test_train_three_temperature_bands_and_forward_test(self):
        result = learning.train_heat_pump(days(), TODAY)
        self.assertEqual(result["status"], "gotowy_podglad")
        self.assertEqual(result["quality"], "oceniony")
        self.assertEqual(result["days_complete"], 14)
        self.assertEqual(result["valid_hours"], 14 * 24)
        self.assertGreaterEqual(result["learned_bands"], 3)
        self.assertAlmostEqual(result["mae_kwh_h"], 0)
        self.assertEqual(learning.predict_pump_w(result, -7), 1800)
        self.assertEqual(learning.predict_pump_w(result, 2), 1200)
        self.assertEqual(learning.predict_pump_w(result, 8), 600)
        self.assertIsNone(learning.predict_pump_w(result, 22))

    def test_holdout_catches_new_larger_pump_load(self):
        records = days()
        key = (TODAY - timedelta(days=1)).isoformat()
        records[key] = fixture(TODAY - timedelta(days=1), power_factor=1.8)
        result = learning.train_heat_pump(records, TODAY)
        self.assertGreater(result["mae_kwh_h"], 0)
        self.assertGreater(result["bias_actual_minus_model_kwh_h"], 0)

    def test_today_and_future_are_excluded(self):
        records = days()
        records[TODAY.isoformat()] = fixture(TODAY, power_factor=20)
        records[(TODAY + timedelta(days=1)).isoformat()] = fixture(TODAY, power_factor=20)
        result = learning.train_heat_pump(records, TODAY)
        self.assertEqual(result["valid_hours"], 336)
        self.assertAlmostEqual(result["mae_kwh_h"], 0)

    def test_incomplete_hours_and_dst_repeated_hour_are_rejected(self):
        records = days()
        item = records[(TODAY - timedelta(days=1)).isoformat()]
        item["coverage"]["heat_pump"]["00:00"] = .7
        item["temperature_coverage"]["01:00"] = .6
        item["temperature_coverage"]["02:00"] = 2.
        result = learning.train_heat_pump(records, TODAY)
        self.assertEqual(result["valid_hours"], 336 - 3)
        self.assertEqual(result["status"], "gotowy_podglad")

    def test_untrained_temperature_band_is_explicit_unknown(self):
        records = days()
        for row in records.values():
            for h in range(16, 24):
                row["temperature_degree_hours"][f"{h:02}:00"] = 2.
        model = learning.train_heat_pump(records, TODAY)
        self.assertIsNone(learning.predict_pump_w(model, -25))
        self.assertIsNone(learning.predict_pump_w(model, 20))

    def test_preview_is_read_only_and_compares_same_weather_hours(self):
        model = learning.train_heat_pump(days(), TODAY)
        now = datetime(2026, 11, 23, 12, tzinfo=TZ)
        temperatures = [engine.TempSlot(
            now.astimezone(timezone.utc) + timedelta(hours=i), 2.0
        ) for i in range(49)]
        preview = learning.preview_48h(
            now, temperatures, 2, model, mild_w=600, cold_w=1200
        )
        self.assertEqual(preview["status"], "porownanie_wstepne")
        self.assertEqual(preview["porownywalne_godziny"], 48)
        self.assertAlmostEqual(preview["prognoza_nauczona_kwh"], 57.6)
        self.assertFalse(preview["model_wlaczone_do_planowania"])

    def test_no_weather_does_not_fabricate_48_hour_preview(self):
        model = learning.train_heat_pump(days(), TODAY)
        now = datetime(2026, 11, 23, 12, tzinfo=TZ)
        preview = learning.preview_48h(
            now, [], 2., model, mild_w=600, cold_w=1200
        )
        self.assertEqual(preview["status"], "czesciowa_prognoza")
        self.assertEqual(preview["porownywalne_godziny"], 0)
        self.assertIsNone(preview["prognoza_nauczona_kwh"])

    def test_model_never_writes_hardware(self):
        source = (ROOT / "heat_pump_learning.py").read_text()
        for token in ("hass.services.async_call", "number.set_value",
                      "switch.turn_on", "climate.set_temperature"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
