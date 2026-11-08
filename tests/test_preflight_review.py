"""Readable preflight groups never equate configured values with physical safety."""
from __future__ import annotations
import importlib.util
import sys
import types
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"estadi_energy_pilot"
PKG="energy_preflight_review_tests"
module=types.ModuleType(PKG);module.__path__=[str(ROOT)];sys.modules[PKG]=module

def load(name):
    spec=importlib.util.spec_from_file_location(f"{PKG}.{name}",ROOT/f"{name}.py")
    result=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=result
    spec.loader.exec_module(result)
    return result

const=load("const")
review=load("preflight_review")


class PreflightReviewTests(unittest.TestCase):
    def sample(self,*,grid_kw=0.01,battery_kw=-1.4,grid_sign=1,battery_sign=0,
               phases=False,forecast=False):
        statuses={
            const.CONF_GRID_POWER:{"encja":"sensor.deye_grid_power","stan":"ok"},
            const.CONF_BATTERY_POWER:{"encja":"sensor.deye_battery_power","stan":"ok"},
        }
        for k in (
            const.CONF_PHASE_CURRENT_L1,const.CONF_PHASE_CURRENT_L2,const.CONF_PHASE_CURRENT_L3,
            const.CONF_PHASE_VOLTAGE_L1,const.CONF_PHASE_VOLTAGE_L2,const.CONF_PHASE_VOLTAGE_L3,
        ):
            statuses[k]={"stan":"ok" if phases else "brak_encji"}
        guard={
            "source_status":statuses,"raw_grid_kw":grid_kw,
            "raw_battery_kw":battery_kw,"phase_checked":phases,
            "phase_status":"pomiar_3_faz" if phases else "brak_aktualnych_pomiarow_faz",
        }
        settings={const.CONF_GRID_IMPORT_SIGN:grid_sign,
                  const.CONF_BATTERY_CHARGE_SIGN:battery_sign,
                  const.CONF_GRID_LIMIT:15,
                  const.CONF_PHASE_LIMIT_L1:25,
                  const.CONF_PHASE_LIMIT_L2:25,
                  const.CONF_PHASE_LIMIT_L3:25}
        tou={"status":"odczytano_6_programow","odczytane_pola":24,
             "global_grid_charge":"off","tou_mode_raw":"Week","grid_charging_programs":[]}
        sim={"status":"gotowa","forecast_hours":48} if forecast else {
            "status":"niepelna","forecast_hours":42.3}
        plan={"status":"wstepny_plan"} if forecast else {"status":"brak_celu"}
        return review.build_preflight_steps(
            guard=guard,inventory=tou,selected=settings,sim=sim,plan=plan,
            inverter_limit_w=31000,peak_shaving_state="off"
        )

    def test_actual_user_blockers_grouped_without_repetition(self):
        r=self.sample()
        self.assertEqual(r["stage_count"],5)
        self.assertEqual(len(r["groups"]),5)
        self.assertEqual(r["groups"][0]["status"],"wymaga")
        self.assertEqual(r["groups"][0]["evidence"]["battery_kw_raw"],-1.4)
        self.assertEqual(r["groups"][1]["status"],"wymaga")
        self.assertEqual(r["groups"][2]["status"],"odczyt_ok")
        self.assertEqual(r["groups"][2]["evidence"]["read_fields"],24)
        self.assertEqual(r["groups"][3]["status"],"wymaga")
        self.assertEqual(r["groups"][4]["status"],"blokada")
        self.assertIn("Kierunki mocy",r["next_action"])
        self.assertEqual(r["commands_sent"],0)
        self.assertFalse(r["control_enabled"])
        self.assertEqual(len(r["notes"]),2)
        text=" ".join(
            item for group in r["groups"] for item in group["items"])
        self.assertEqual(text.count("BMS"),1)
        self.assertEqual(text.count("Grid Charge"),1)

    def test_after_polarity_setup_phase_check_is_next_action(self):
        r=self.sample(battery_sign=-1)
        self.assertIn("Przyłącze i fazy",r["next_action"])
        self.assertEqual(r["groups"][0]["status"],"ustawiono")
        self.assertEqual(r["groups"][1]["status"],"wymaga")
        self.assertEqual(r["groups"][4]["status"],"blokada")

    def test_after_phases_missing_forecast_is_next(self):
        r=self.sample(battery_sign=-1,phases=True)
        self.assertIn("Prognoza i plan",r["next_action"])
        self.assertEqual(r["groups"][1]["status"],"ustawiono")

    def test_all_software_sources_dont_unlock_physical_control(self):
        r=self.sample(battery_sign=-1,phases=True,forecast=True)
        self.assertEqual(r["groups"][3]["status"],"odczyt_ok")
        self.assertEqual(r["groups"][4]["status"],"blokada")
        self.assertFalse(r["control_enabled"])
        self.assertIn("BMS",r["next_action"])

    def test_missing_sources_are_never_reported_as_zero(self):
        r=self.sample(grid_kw=None,battery_kw=None,grid_sign=0)
        self.assertIsNone(r["groups"][0]["evidence"]["grid_kw_raw"])
        self.assertIsNone(r["groups"][0]["evidence"]["battery_kw_raw"])
        self.assertEqual(r["groups"][0]["status"],"wymaga")

    def test_15kw_connection_independent_of_different_inverter_setting(self):
        r=self.sample()
        self.assertEqual(r["groups"][1]["evidence"]["connection_limit_kw"],15)
        self.assertIn("15 kW",r["notes"][0])
        self.assertIn("8 kW",r["notes"][1])


if __name__=="__main__":
    unittest.main()
