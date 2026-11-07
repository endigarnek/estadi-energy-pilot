"""Evidence-driven commissioning checks from real 2026-11-07 Deye TOU readout.

No Home Assistant service calls or writable adapter is instantiated.
"""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"estadi_energy_pilot"
PKG="tou_commissioning_tests"
pkg=ModuleType(PKG);pkg.__path__=[str(ROOT)];sys.modules[PKG]=pkg
def load(name):
    spec=importlib.util.spec_from_file_location(f"{PKG}.{name}",ROOT/f"{name}.py")
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod
    spec.loader.exec_module(mod);return mod

tou=load("deye_tou")
commission=load("tou_commissioning")
NOW=datetime(2026,11,7,14,3,tzinfo=timezone.utc)


def state(entity,value,unit=None):
    return SimpleNamespace(entity_id=entity,state=str(value),attributes=(
        {"unit_of_measurement":unit} if unit else {}))


def real_config(times=("01:00","05:00","09:00","13:00","17:00","21:00")):
    items=[
        state("select.deye_time_of_use","Week"),
        state("switch.deye_battery_grid_charging","off"),
        state("select.deye_battery_bms_type","PYLON"),
        state("number.deye_battery_grid_charging_current",40,"A"),
        state("number.deye_battery_max_charging_current",200,"A"),
        state("number.deye_grid_max_import_power",31000,"W"),
    ]
    for n,t in enumerate(times,1):
        items.extend([
            state(f"time.deye_program_{n}_time",t),
            state(f"number.deye_program_{n}_soc",10,"%"),
            state(f"number.deye_program_{n}_power",15000,"W"),
            state(f"select.deye_program_{n}_charging","Disabled"),
        ])
    return items


class CommissioningTests(unittest.TestCase):
    def audit(self,items=None,plan=None):
        states=real_config() if items is None else items
        index={x.entity_id:x for x in states}
        inv=tou.inspect_tou(states,NOW)
        return commission.audit_tou_map(inv,plan=plan,get_state=index.get)

    def test_full_24_fields_is_not_write_permission(self):
        report=self.audit()
        self.assertEqual(report["readback_status"],"ok")
        self.assertEqual(report["readback_fields"],24)
        self.assertEqual(report["operational_status"],"blokada")
        self.assertFalse(report["can_write"])
        self.assertEqual(report["commands_sent"],0)
        self.assertEqual(report["write_actions"],[])
        self.assertFalse(report["snapshot_persisted"])
        self.assertFalse(report["safe_rollback_proven"])
        self.assertTrue(report["snapshot_in_memory"])
        self.assertEqual(report["active_grid_programs"],[])
        self.assertTrue(report["time_order_valid"])
        self.assertIn("Grid Charge",str(report["blockers"]))

    def test_0150_to_0445_does_not_match_0100_0500_tou(self):
        plan={"start":"2026-11-09T01:30:00+01:00",
              "end_window":"2026-11-09T04:45:00+01:00"}
        report=self.audit(plan=plan)
        self.assertEqual(report["window_alignment"]["plan_start_local"],"01:30")
        self.assertEqual(report["window_alignment"]["plan_end_local"],"04:45")
        self.assertFalse(report["window_alignment"]["start_aligned"])
        self.assertFalse(report["window_alignment"]["end_aligned"])
        self.assertIn("nie pokrywa",str(report["blockers"]))
        self.assertEqual(report["write_actions"],[])

    def test_matching_schedule_boundaries_still_do_not_prove_bms_or_write(self):
        plan={"start":"2026-11-09T01:00:00+01:00",
              "end_window":"2026-11-09T05:00:00+01:00"}
        report=self.audit(plan=plan)
        self.assertTrue(report["window_alignment"]["start_aligned"])
        self.assertTrue(report["window_alignment"]["end_aligned"])
        self.assertFalse(report["can_write"])

    def test_duplicate_clock_times_are_blocked(self):
        report=self.audit(items=real_config(times=(
            "01:00","05:00","09:00","13:00","17:00","17:00"
        )))
        self.assertFalse(report["time_order_valid"])
        self.assertIn("unikalność",str(report["blockers"]))

    def test_no_model_time_or_wrong_firmware_cannot_arm(self):
        bad=real_config()
        bad=[x for x in bad if x.entity_id!="time.deye_program_3_time"]
        report=self.audit(items=bad,plan={"start":"08:00"})
        self.assertEqual(report["readback_status"],"niekompletne")
        self.assertFalse(report["can_write"])
        self.assertFalse(report["snapshot_in_memory"])
        self.assertFalse(report["model_firmware_verified"])

    def test_missing_one_global_setting_keeps_readback_but_no_control(self):
        raw=[x for x in real_config()
             if x.entity_id!="number.deye_battery_grid_charging_current"]
        report=self.audit(items=raw)
        self.assertEqual(report["readback_status"],"ok")
        self.assertIn("number.deye_battery_grid_charging_current",
                      str(report["blockers"]))
        self.assertFalse(report["can_write"])


if __name__=="__main__":
    unittest.main()
