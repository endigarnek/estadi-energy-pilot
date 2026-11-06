"""Regression tests for honest historical heat-pump excess diagnostics."""
from __future__ import annotations

from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot"
PKG = "pilot_pump_excess_tests"
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


load("engine")
load("tariffs")
load("simulation_48h")
load("heat_pump_learning")
pump = load("pump_excess")
TODAY = date(2026, 11, 25)


def record(*, baseline=1.2, extra_hours=None, missing=None, weather=2.):
    extra_hours = extra_hours or {}
    missing = missing or []
    result = {
        "actual": {"heat_pump": {}},
        "coverage": {"heat_pump": {}},
        "temperature_degree_hours": {},
        "temperature_coverage": {},
    }
    for hour in range(24):
        key = f"{hour:02d}:00"
        result["actual"]["heat_pump"][key] = baseline + extra_hours.get(hour, 0.)
        result["coverage"]["heat_pump"][key] = 1. if hour not in missing else .4
        result["temperature_degree_hours"][key] = weather
        result["temperature_coverage"][key] = 1. if hour not in missing else .4
    return result


def history(days=14):
    return {
        (TODAY - timedelta(days=offset)).isoformat(): record()
        for offset in range(days, 0, -1)
    }


class PumpExcessTests(unittest.TestCase):
    def test_zero_false_positives_for_stable_heat_pump(self):
        report = pump.inspect_pump_excess(history(), TODAY)
        self.assertEqual(report["status"], "oceniono_odchylenia")
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["suspected_high_load_hours"], 0)
        self.assertEqual(report["estimated_excess_energy_kwh"], 0)
        self.assertGreater(report["hours_compared_with_older_days"], 24)
        self.assertFalse(report["automatic_actions"])
        self.assertIsNone(report["confirmed_dhw_cycles"])
        self.assertIsNone(report["confirmed_defrost_cycles"])

    def test_two_events_group_consecutive_hours_with_excess_energy(self):
        days = history()
        last = (TODAY - timedelta(days=1)).isoformat()
        days[last] = record(extra_hours={10: 1.2, 11: 1.4, 16: 1.0})
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["event_count"], 2)
        self.assertEqual(report["suspected_high_load_hours"], 3)
        self.assertAlmostEqual(report["estimated_excess_energy_kwh"], 3.6)
        events = report["latest_events"]
        self.assertEqual(events[0]["hours"], 2)
        self.assertEqual(events[1]["hours"], 1)
        self.assertEqual(events[0]["start"], last + "T10:00:00")
        self.assertEqual(events[0]["end"], last + "T12:00:00")
        self.assertEqual(events[0]["cause"], "nieustalona")
        self.assertTrue(events[0]["possible_causes_not_verified"])

    def test_missing_hour_does_not_create_or_join_an_event(self):
        days = history()
        last = (TODAY - timedelta(days=1)).isoformat()
        days[last] = record(extra_hours={10: 2, 11: 2, 12: 2}, missing=[11])
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["event_count"], 2)
        self.assertEqual(report["suspected_high_load_hours"], 2)
        self.assertEqual([event["hours"] for event in report["latest_events"]], [1, 1])

    def test_overweight_hour_is_never_trained_on_its_own_day(self):
        days = history()
        key = (TODAY - timedelta(days=1)).isoformat()
        days[key] = record(extra_hours={18: 4})
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["event_count"], 1)
        self.assertEqual(report["last_event_start"], key + "T18:00:00")

    def test_current_and_future_days_are_excluded(self):
        days = history()
        days[TODAY.isoformat()] = record(extra_hours={5: 10})
        days[(TODAY + timedelta(days=1)).isoformat()] = record(extra_hours={5: 10})
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["historical_days_seen"], 14)

    def test_missing_temperature_is_unknown_not_zero_or_normal(self):
        days = history()
        for item in days.values():
            item["temperature_degree_hours"].clear()
            item["temperature_coverage"].clear()
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["status"], "zbieranie_danych")
        self.assertEqual(report["hours_with_temperature_and_energy"], 0)
        self.assertIsNone(report["event_count"])
        self.assertIsNone(report["estimated_excess_energy_kwh"])

    def test_first_days_do_not_have_a_learned_reference(self):
        days = history(days=3)
        last = (TODAY - timedelta(days=1)).isoformat()
        days[last] = record(extra_hours={9: 5})
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["status"], "zbieranie_danych")
        self.assertEqual(report["event_count"], None)
        self.assertLess(report["hours_compared_with_older_days"], 24)

    def test_sparse_temperature_band_is_not_extrapolated(self):
        days = history()
        last = (TODAY - timedelta(days=1)).isoformat()
        days[last] = record(weather=-30., extra_hours={9: 10})
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["suspected_high_load_hours"], 0)

    def test_high_historical_p90_does_not_trigger_small_spike(self):
        days = history()
        last = (TODAY - timedelta(days=1)).isoformat()
        days[last] = record(extra_hours={9: .45, 10: .25})
        report = pump.inspect_pump_excess(days, TODAY)
        self.assertEqual(report["event_count"], 0)

    def test_never_claim_cycles_or_control_hardware(self):
        source = (ROOT / "pump_excess.py").read_text(encoding="utf-8")
        for forbidden in ("hass.services", "number.set_value",
                          "switch.turn_on", "climate.set_temperature"):
            self.assertNotIn(forbidden, source)
        report = pump.inspect_pump_excess(history(), TODAY)
        self.assertFalse(report["automatic_actions"])
        self.assertIn("NIE można ustalić", report["interpretation"])


if __name__ == "__main__":
    unittest.main()
