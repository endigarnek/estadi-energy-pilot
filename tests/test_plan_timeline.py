"""48h operational plan: hourly SOC, grid charging and discharge consistency."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PKG="energy_plan_timeline_tests"
package=types.ModuleType(PKG); package.__path__=[str(ROOT)]; sys.modules[PKG]=package

def load(name):
    spec=importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT/f"{name}.py")
    obj=importlib.util.module_from_spec(spec);sys.modules[spec.name]=obj;spec.loader.exec_module(obj);return obj

battery=load("battery_model")
engine=load("engine")
tariffs=load("tariffs")
geometry=load("solar_geometry")
simulation=load("simulation_48h")
economics=load("scenario_economics")
timeline=load("plan_timeline")
TZ=ZoneInfo("Europe/Warsaw")


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,7,1,0,tzinfo=TZ)
        self.model=battery.BatteryModel(nominal_kwh=28,minimum_soc=10,maximum_soc=100)
        start=self.now.astimezone(timezone.utc)
        self.slots=[engine.PvSlot(start+timedelta(hours=i),0.,60) for i in range(49)]
        self.plan={"status":"wstepny_plan",
                   "start":datetime(2026,11,7,1,30,tzinfo=TZ).isoformat(),
                   "end_window":datetime(2026,11,7,7,0,tzinfo=TZ).isoformat(),
                   "power_kw":5., "target_soc":75.}
    def compare(self,plan="default",pv=None,**kw):
        candidate=self.plan if plan=="default" else plan
        cfg=dict(now=self.now,pv_slots=self.slots if pv is None else pv,
                 temperatures=[],learning={"baseline_ready":False},
                 model=self.model,soc=15,current_temp=10,tariff="G12w",
                 prices={"cheap":0.45,"peak":1.1},proposed_plan=candidate,
                 export_value_pln_kwh=None,baseload_w=500,mild_w=0,cold_w=0,
                 pv_discount_pct=0,efficiency_pct=90,battery_max_kw=10,
                 grid_limit_kw=15,grid_buffer_kw=2,ev_now_kw=0,
                 latitude=50.8,longitude=19.1)
        cfg.update(kw)
        return economics.compare_scenarios(**cfg)
    def test_two_real_simulated_trajectories_and_energy_match(self):
        ec=self.compare()
        self.assertEqual(ec["baseline"]["status"],"gotowy")
        self.assertEqual(ec["plan"]["status"],"gotowy")
        result=timeline.build_plan_timeline(ec)
        self.assertEqual(result["status"],"gotowy")
        self.assertEqual(result["hours"],48)
        self.assertEqual(result["planned_hours"],48)
        self.assertGreater(result["charge_from_grid_kwh"],0)
        self.assertFalse(ec["plan_written_to_deye"])
        self.assertEqual(result["deye_commands_sent"],0)
        self.assertTrue(result["forecast_not_execution"])
        rows=result["timeline"]
        self.assertTrue(any(r["tryb"]=="ladowanie_z_sieci" for r in rows))
        self.assertTrue(any(r["tryb"]=="rozladowanie" for r in rows))
        self.assertAlmostEqual(sum(r["ladowanie_siec_kwh"] or 0 for r in rows),
                               ec["plan"]["grid_battery_kwh"],delta=.02)
        self.assertAlmostEqual(sum(r["rozladowanie_kwh"] or 0 for r in rows),
                               ec["plan"]["battery_to_load_kwh"],delta=.02)
        self.assertEqual(rows[0]["czas"],ec["plan"]["timeline_hours"][0]["czas"])
    def test_no_plan_is_baseline_only_not_claimed_automation(self):
        ec=self.compare(plan={"status":"brak_celu"})
        result=timeline.build_plan_timeline(ec)
        self.assertEqual(result["status"],"brak_planu")
        self.assertEqual(result["hours"],48)
        self.assertEqual(result["planned_hours"],0)
        self.assertIsNone(result["charge_from_grid_kwh"])
        self.assertTrue(all(row["soc_plan_pct"] is None for row in result["timeline"]))
    def test_partial_daylight_forecast_does_not_claim_full_totals(self):
        ec=self.compare(pv=self.slots[:12])
        out=timeline.build_plan_timeline(ec)
        self.assertEqual(out["status"],"niepelna_prognoza")
        self.assertLess(out["hours"],48)
        self.assertIsNone(out["charge_from_grid_kwh"])
        self.assertIsNone(out["planned_grid_import_kwh"])
    def test_misaligned_timeline_never_joins_wrong_hours(self):
        data={"status":"gotowy","hours":48,"timeline_hours":[
            {"czas":"2026-11-07 01:00+0100","soc_end":20}]}
        bad={"status":"gotowy","hours":48,"timeline_hours":[
            {"czas":"2026-11-07 02:00+0100","soc_end":50}]}
        out=timeline.build_plan_timeline({"baseline":data,"plan":bad})
        self.assertEqual(out["status"],"blad_wyrownania")
        self.assertEqual(out["timeline"],[])
    def test_winter_forecast_without_night_rows_scenario_is_complete(self):
        # An hourly provider with solar-only hours still supports a full
        # physical comparison without inventing midday values.
        sunny=[]
        for day in (7,8,9):
            for hour in range(7,17):
                at=datetime(2026,11,day,hour,tzinfo=TZ).astimezone(timezone.utc)
                sunny.append(engine.PvSlot(at,2.,60))
        econ=self.compare(pv=sunny)
        self.assertEqual(econ["baseline"]["status"],"gotowy",econ)
        self.assertEqual(econ["baseline"]["hours"],48)


if __name__=="__main__":
    unittest.main()
