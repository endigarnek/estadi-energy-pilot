"""Offline tests for read-only Energy Pilot lab; never send a Deye command."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"estadi_energy_pilot"
NAME="pilot_lab_safety_tests"
package=types.ModuleType(NAME)
package.__path__=[str(ROOT)]
sys.modules[NAME]=package

def load(name):
    spec=importlib.util.spec_from_file_location(f"{NAME}.{name}",ROOT/f"{name}.py")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

const=load("const")
load("grid_guard")
load("grid_monitor")
load("deye_tou")
lab=load("lab_checks")
NOW=datetime(2026,11,7,1,0,tzinfo=timezone.utc)

def sample(entity_id,value,unit="W",ago=2):
    return SimpleNamespace(entity_id=entity_id,state=str(value),
      attributes={"unit_of_measurement":unit},
      last_reported=NOW-timedelta(seconds=ago),last_updated=NOW-timedelta(seconds=ago))
class FakeStates:
    def __init__(self,d):self.data=d
    def get(self,k):return self.data.get(k)
    def async_all(self):return list(self.data.values())

class LabTests(unittest.TestCase):
    def setUp(self):
        self.settings={**const.DEFAULTS,
            const.CONF_GRID_POWER:"sensor.deye_grid_power",
            const.CONF_BATTERY_POWER:"sensor.deye_battery_power"}
        self.states=FakeStates({
            "sensor.deye_grid_power":sample("sensor.deye_grid_power",1764),
            "sensor.deye_battery_power":sample("sensor.deye_battery_power",13),
            "number.deye_program_1_power":sample("number.deye_program_1_power",5000)
        })
    def check(self,kind):
        return lab.inspect_test(kind,states=self.states,
            selected=self.settings,coordinator_data={"energy_2_0":{}},now=NOW)
    def test_measurement_does_not_assume_polariy(self):
        r=self.check("meters")
        self.assertEqual(r["status"],"ok")
        self.assertEqual(r["grid_signed_kw"],1.764)
        self.assertEqual(r["battery_signed_kw"],0.013)
        self.assertFalse(r["command_sent"])
        self.assertFalse(r["actual_power_change_verified"])
    def test_missing_sign_blocks_and_cannot_send(self):
        r=self.check("polarity")
        self.assertEqual(r["status"],"blokada")
        self.assertFalse(r["hardware_verified"])
        self.assertEqual(r["grid_sign"],0)
    def test_grid_guard_remains_closed(self):
        r=self.check("limits")
        self.assertEqual(r["status"],"blokada")
        self.assertIsNone(r["allowed_charge_kw"])
    def test_incomplete_forecast_is_explained(self):
        result=lab.inspect_test("forecast",states=self.states,
            selected=self.settings,
            coordinator_data={"energy_2_0":{
                "simulation_48h":{"status":"niepelna_prognoza_pv",
                 "forecast_hours":2.75,"reason":"Brak godzinowej prognozy"},
                "optimized_schedule":{"status":"brak_celu"}}},
            now=NOW)
        self.assertEqual(result["status"],"blokada")
        self.assertEqual(result["hours"],2.75)
    def test_write_discovery_cannot_actuate_even_when_candidates_exist(self):
        r=self.check("write_capability")
        self.assertEqual(r["status"],"blokada")
        self.assertEqual(r["discovered"],1)
        self.assertFalse(r["actual_write_test_available"])
        self.assertFalse(r["command_sent"])
    def test_write_candidate_metadata_has_range_but_never_proves_write(self):
        ent=self.states.data["number.deye_program_1_power"]
        ent.attributes.update(
            friendly_name="Deye TOU Program 1 Power",
            min=0, max=5000, step=100,unit_of_measurement="W")
        r=self.check("write_capability")
        c=r["candidates"][0]
        self.assertEqual(c["min"],0)
        self.assertEqual(c["max"],5000)
        self.assertEqual(c["step"],100)
        self.assertEqual(c["label"],"Deye TOU Program 1 Power")
        self.assertFalse(c["command_written"])
        self.assertFalse(c["readback_verified"])
        self.assertFalse(r["actual_write_test_available"])

    def test_preflight_remains_locked_even_if_all_virtual_checks_pass(self):
        # This is a reminder to verify BMS, rollback and physical readback.
        result=lab.inspect_test(
            "preflight", states=self.states,
            selected=self.settings,
            coordinator_data={"energy_2_0":{
                "simulation_48h":{"status":"gotowa","forecast_hours":48},
                "optimized_schedule":{"status":"wstepny_plan"},
                "pv_coverage":{"source":"Forecast.Solar"}}},
            now=NOW)
        self.assertEqual(result["status"],"blokada")
        self.assertFalse(result["command_sent"])
        self.assertFalse(result["remote_control_enabled"])
        self.assertFalse(result["write_test_approved"])
        self.assertIn("BMS",str(result["blockers"]))

    def test_same_device_inventory_discovers_controls_without_deye_in_slug(self):
        self.states.data["number.program_01_battery_power"] = sample(
            "number.program_01_battery_power", 2500)
        self.states.data["number.unrelated_power"] = sample(
            "number.unrelated_power", 2000)
        r=lab.inspect_test(
            "write_capability", states=self.states, selected=self.settings,
            coordinator_data={"energy_2_0":{}}, now=NOW,
            same_deye_device_entities={"number.program_01_battery_power"})
        names=[entry["entity"] for entry in r["candidates"]]
        self.assertIn("number.program_01_battery_power", names)
        self.assertNotIn("number.unrelated_power", names)
        self.assertEqual(r["candidates"][0]["detected_by"],"same_deye_device")
        self.assertFalse(r["command_sent"])

    def test_unavailable_source_is_not_silently_zero(self):
        self.states.data["sensor.deye_grid_power"]=sample("sensor.deye_grid_power",1500,ago=500)
        r=self.check("meters")
        self.assertEqual(r["status"],"blokada")
        self.assertIsNone(r["grid_signed_kw"])
    def test_code_has_no_dangerous_actions(self):
        src=(ROOT/"lab_checks.py").read_text()
        for forbidden in ("hass.services.async_call","hass.callService",
                          "number.set_value","switch.turn_on","select.select_option"):
            self.assertNotIn(forbidden,src)

if __name__=="__main__":
    unittest.main()
