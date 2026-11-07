"""Regression of winter's false 04:00 forecast gap and daylight safety."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PACKAGE = "energy_daylight_regression"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load("engine")
model = load("battery_model")
tariffs = load("tariffs")
geometry = load("solar_geometry")
simulation = load("simulation_48h")
advisor = load("charging_48h")
WARSAW = ZoneInfo("Europe/Warsaw")
LATITUDE, LONGITUDE = 50.8, 19.1


def daylight_only_slots(start, days=3):
    """Typical Forecast.Solar response: sunlight hours ONLY (no night rows)."""
    local = start.astimezone(WARSAW)
    begin = datetime(local.year, local.month, local.day, 7, tzinfo=WARSAW)
    return [
        engine.PvSlot((begin + timedelta(days=day, hours=hour-7)).astimezone(timezone.utc),
                      2.4 if 9 <= hour < 14 else 0.5, 60)
        for day in range(days)
        for hour in range(7, 17)
    ]


class WinterCoverageTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 7, 1, 33, tzinfo=WARSAW)
        self.pv = daylight_only_slots(self.now)
        self.battery = model.BatteryModel(nominal_kwh=28, minimum_soc=10, maximum_soc=100)

    def simulate(self, slots=None, **geo):
        return simulation.simulate_48h(
            self.now, self.pv if slots is None else slots, [],
            {"baseline_ready":False}, self.battery, 20, 10,
            tariff="G12w", baseload_w=600, mild_w=600,
            cold_w=1200, pv_discount_pct=10, efficiency_pct=90,
            battery_max_kw=10, grid_limit_kw=15, ev_now_kw=0, **geo)

    def test_november_04_00_is_astronomical_night(self):
        t = datetime(2026,11,7,4,0,tzinfo=WARSAW)
        self.assertLess(geometry.solar_elevation(t, LATITUDE, LONGITUDE), -15)
        self.assertFalse(geometry.required_forecast(t,latitude=LATITUDE,longitude=LONGITUDE))
        self.assertTrue(geometry.required_forecast(t,legacy_hours=(4,22)))

    def test_daylight_only_forecast_still_supports_complete_48h(self):
        sim = self.simulate(latitude=LATITUDE, longitude=LONGITUDE)
        self.assertEqual(sim["status"],"gotowa",sim["reason"])
        self.assertEqual(sim["forecast_hours"],48)
        self.assertEqual(len(sim["timeline_hours"]),48)
        self.assertGreater(sim["lowlight_assumed_zero_steps"],10)
        self.assertGreater(sim["pv_kwh"],0)
        report = geometry.summarize_forecast(self.now,self.pv,latitude=LATITUDE,longitude=LONGITUDE)
        self.assertEqual(report["missing_daylight_steps"],0,report)
        self.assertEqual(report["covered_daylight_pct"],100.0)

    def test_missing_actual_midday_forecast_remains_blocked(self):
        midday = datetime(2026,11,8,12,0,tzinfo=WARSAW).astimezone(timezone.utc)
        slots = [slot for slot in self.pv if slot.start != midday]
        sim = self.simulate(slots, latitude=LATITUDE,longitude=LONGITUDE)
        self.assertEqual(sim["status"],"niepelna_prognoza_pv")
        self.assertLess(sim["forecast_hours"],48)
        report = geometry.summarize_forecast(self.now,slots,latitude=LATITUDE,longitude=LONGITUDE)
        self.assertGreater(report["missing_daylight_steps"],0)
        self.assertIsNotNone(report["first_missing_daylight_at"])

    def test_without_location_legacy_guard_remains_strict(self):
        sim=self.simulate()
        self.assertEqual(sim["status"],"niepelna_prognoza_pv")
        self.assertLess(sim["forecast_hours"],5)

    def test_forecast_is_location_based_not_browser_time(self):
        t=datetime(2026,6,7,3,30,tzinfo=WARSAW)
        self.assertFalse(geometry.required_forecast(
            t,latitude=LATITUDE,longitude=LONGITUDE))
        self.assertTrue(geometry.required_forecast(
            datetime(2026,6,7,12,0,tzinfo=WARSAW),latitude=LATITUDE,longitude=LONGITUDE))

    def test_forecast_gaps_cannot_be_filled_by_overlapping_pv_values(self):
        # Slot intervals of 60 min overlap if same timestamp repeats; coverage
        # must be bounded by 1 rather than incorrectly count two time spans.
        slot = self.pv[0]
        c = geometry.slot_coverage(slot.start,slot.start+timedelta(minutes=15),[slot,slot])
        self.assertEqual(c,1.0)

    def test_advisor_allows_nighttime_missing_provider_rows_but_not_daylight(self):
        # A G12w weekend morning cheap window may extend into daylight.
        w=(datetime(2026,11,7,2,0,tzinfo=WARSAW),
           datetime(2026,11,7,8,0,tzinfo=WARSAW))
        args=dict(now=self.now,window=w,soc=20,target_soc=35,model=self.battery,
                  pv_slots=self.pv,temperatures=[],learning={"baseline_ready":False},
                  current_temp=10,tariff="G12w",baseload_w=500,mild_w=600,cold_w=1200,
                  pv_discount_pct=10,efficiency_pct=90,battery_max_kw=10,
                  grid_limit_kw=15,grid_buffer_kw=2,preferred_kw=5,ev_now_kw=0,
                  latitude=LATITUDE,longitude=LONGITUDE)
        result=advisor.recommend_charge(**args)
        self.assertNotEqual(result["status"],"brak_prognozy_pv",result)
        # But when even the full daytime period is missing, it must stop.
        args["pv_slots"]=[]
        missing=advisor.recommend_charge(**args)
        self.assertEqual(missing["status"],"brak_prognozy_pv")


if __name__=="__main__":
    unittest.main()
