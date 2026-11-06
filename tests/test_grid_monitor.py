"""Offline regression tests for Grid Guard phase-source freshness and diagnostics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PACKAGE = "pilot_grid_monitor_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


const = load("const")
guard = load("grid_guard")
monitor = load("grid_monitor")

NOW = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)


def sensor(value, unit, *, age=2, reported=True):
    return SimpleNamespace(
        state=str(value),
        attributes={"unit_of_measurement": unit},
        last_reported=NOW - timedelta(seconds=age) if reported else None,
        last_updated=NOW - timedelta(seconds=age),
    )


class GridMonitorTests(unittest.TestCase):
    def setUp(self):
        self.settings = {**const.DEFAULTS,
                         const.CONF_GRID_POWER: "sensor.deye_grid_power",
                         const.CONF_BATTERY_POWER: "sensor.deye_battery_power",
                         const.CONF_GRID_IMPORT_SIGN: 1,
                         const.CONF_BATTERY_CHARGE_SIGN: 1}
        self.states = {
            "sensor.deye_grid_power": sensor(12000, "W"),
            "sensor.deye_battery_power": sensor(3000, "W"),
        }

    def evaluate(self):
        return monitor.build_grid_readout(self.states.get, self.settings, NOW)

    def test_import_already_includes_ev_pump_and_charge(self):
        result = self.evaluate()
        self.assertAlmostEqual(result["import_kw"], 12)
        self.assertAlmostEqual(result["current_charge_kw"], 3)
        # 12kW existing import includes the 3kW grid charging already:
        # soft limit 13kW = can raise battery charging by 1kW to 4kW.
        self.assertAlmostEqual(result["allowed_charge_kw"], 4)
        self.assertFalse(result["automatic_ready"])
        self.assertFalse(result["phase_checked"])

    def test_ev_stops_and_charge_headroom_increases(self):
        before = self.evaluate()
        self.states["sensor.deye_grid_power"] = sensor(3000, "W")
        self.states["sensor.deye_battery_power"] = sensor(0, "W")
        after = self.evaluate()
        self.assertLess(before["allowed_charge_kw"], after["allowed_charge_kw"])
        self.assertAlmostEqual(after["allowed_charge_kw"], 10)

    def test_raw_grid_power_visible_with_unconfirmed_sign_but_never_treated_as_import(self):
        self.settings[const.CONF_GRID_IMPORT_SIGN] = 0
        result = self.evaluate()
        self.assertEqual(result["state"], "blokada")
        self.assertEqual(result["raw_grid_kw"], 12.0)
        self.assertEqual(result["raw_grid_status"], "ok")
        self.assertEqual(result["raw_grid_entity_id"], "sensor.deye_grid_power")
        self.assertIsNone(result["raw_grid_is_import"])
        self.assertIsNone(result["import_kw"])
        self.assertIsNone(result["headroom_kw"])
        self.assertIsNone(result["allowed_charge_kw"])

    def test_raw_grid_power_unavailable_if_sensor_is_stale(self):
        self.settings[const.CONF_GRID_IMPORT_SIGN] = 0
        self.states["sensor.deye_grid_power"] = sensor(5000, "W", age=300)
        result = self.evaluate()
        self.assertIsNone(result["raw_grid_kw"])
        self.assertEqual(result["raw_grid_status"], "dane_nieaktualne")

    def test_missing_sign_fails_closed(self):
        self.settings[const.CONF_GRID_IMPORT_SIGN] = 0
        result = self.evaluate()
        self.assertEqual(result["state"], "blokada")
        self.assertIsNone(result["allowed_charge_kw"])
        self.assertFalse(result["import_sign_confirmed"])

    def test_old_grid_state_is_not_usable(self):
        self.states["sensor.deye_grid_power"] = sensor(3000, "W", age=300)
        result = self.evaluate()
        self.assertEqual(result["state"], "blokada")
        self.assertEqual(result["source_status"][const.CONF_GRID_POWER]["stan"],
                         "dane_nieaktualne")

    def test_wrong_unit_not_accepted(self):
        self.states["sensor.deye_grid_power"] = sensor(12, "kWh")
        result = self.evaluate()
        self.assertIsNone(result["allowed_charge_kw"])
        self.assertEqual(result["source_status"][const.CONF_GRID_POWER]["stan"],
                         "bledna_jednostka")

    def test_three_phase_verified_measurements_without_automation(self):
        self._set_phases()
        result = self.evaluate()
        self.assertTrue(result["phase_checked"])
        self.assertEqual(result["phase_status"], "pomiar_3_faz")
        self.assertFalse(result["automatic_ready"])

    def test_single_phase_near_limit_restricts_total_charging(self):
        self._set_phases()
        # With 16A breaker and 15A on L2, balanced additional charging
        # is constrained to ~0.69kW; not the whole-site headroom.
        self.states["sensor.grid_l2_current"] = sensor(15, "A")
        result = self.evaluate()
        self.assertLessEqual(result["allowed_charge_kw"], 3.69)
        self.assertTrue(result["phase_checked"])

    def test_stale_one_phase_blocks_verified_phase_status(self):
        self._set_phases()
        self.states["sensor.grid_l3_current"] = sensor(7, "A", age=200)
        result = self.evaluate()
        self.assertFalse(result["phase_checked"])
        self.assertEqual(result["phase_status"], "brak_aktualnych_pomiarow_faz")
        self.assertFalse(result["automatic_ready"])

    def test_phase_limits_unknown_are_never_guessed(self):
        self._set_phases()
        self.settings[const.CONF_PHASE_LIMIT_L2] = 0
        result = self.evaluate()
        self.assertFalse(result["phase_checked"])
        self.assertEqual(result["phase_status"], "brak_limitu_pradu_faz")

    def test_missing_reported_timestamp_fails_closed(self):
        self.states["sensor.deye_grid_power"] = SimpleNamespace(
            state="12000", attributes={"unit_of_measurement": "W"},
            last_updated=None, last_reported=None,
        )
        result = self.evaluate()
        self.assertIsNone(result["allowed_charge_kw"])
        self.assertEqual(result["source_status"][const.CONF_GRID_POWER]["stan"],
                         "brak_znacznika_czasu")

    def _set_phases(self):
        for idx, (curr, volt, limit) in enumerate(zip(
            monitor.PHASE_CURRENT_KEYS, monitor.PHASE_VOLTAGE_KEYS,
            monitor.PHASE_LIMIT_KEYS
        ), 1):
            self.settings[curr] = f"sensor.grid_l{idx}_current"
            self.settings[volt] = f"sensor.grid_l{idx}_voltage"
            self.settings[limit] = 16.0
            self.states[f"sensor.grid_l{idx}_current"] = sensor(8, "A")
            self.states[f"sensor.grid_l{idx}_voltage"] = sensor(230, "V")


if __name__ == "__main__":
    unittest.main()
