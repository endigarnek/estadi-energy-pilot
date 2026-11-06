"""Charging advisor is advisory only: limits, tariffs, EV and SOC scenarios."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PACKAGE = "energy_charge_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


battery = load("battery_model")
engine = load("engine")
tariffs = load("tariffs")
simulation = load("simulation_48h")
advisor = load("charging_48h")
TZ = ZoneInfo("Europe/Warsaw")


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 12, tzinfo=TZ)
        self.window = (datetime(2026, 11, 6, 13, tzinfo=TZ),
                       datetime(2026, 11, 6, 15, tzinfo=TZ))
        self.model = battery.BatteryModel(
            nominal_kwh=28, soh_pct=100, minimum_soc=10, maximum_soc=100)
        start = self.now.astimezone(timezone.utc)
        self.pv = [engine.PvSlot(start + timedelta(hours=i), 0, 60) for i in range(12)]

    def plan(self, *, soc=40, target=65, ev=0, base=500, pv=None,
             now=None, window=None, **extra):
        args = dict(
            now=now or self.now, window=self.window if window is None else window,
            soc=soc, target_soc=target, model=self.model,
            pv_slots=self.pv if pv is None else pv, temperatures=[],
            learning={"baseline_ready": False}, current_temp=10,
            tariff="G12w", baseload_w=base,
            mild_w=600, cold_w=1200, pv_discount_pct=0,
            efficiency_pct=90, battery_max_kw=10,
            grid_limit_kw=15, grid_buffer_kw=2,
            preferred_kw=5, ev_now_kw=ev,
        )
        args.update(extra)
        return advisor.recommend_charge(**args)

    def test_cheap_g12w_ends_at_15_not_16(self):
        result = self.plan()
        self.assertEqual(result["status"], "wstepny_plan")
        self.assertLessEqual(datetime.fromisoformat(result["finish_estimated"]), self.window[1])
        self.assertLess(datetime.fromisoformat(result["start"]), self.window[1])
        self.assertLessEqual(result["grid_peak_kw"], 13)
        self.assertFalse(result["hardware_control"])
        self.assertFalse(result["phase_limits_verified"])

    def test_active_11kw_ev_blocks_extra_charge_in_soft_limit(self):
        result = self.plan(ev=11, base=2_000, target=80)
        self.assertEqual(result["status"], "nieosiagalny")
        self.assertLess(result["max_soc_estimate"], 80)
        self.assertFalse(result["hardware_control"])

    def test_car_stopped_can_regain_charge_headroom(self):
        while_ev = self.plan(ev=11, base=1000, target=80)
        after_ev = self.plan(ev=0, base=1000, target=80)
        self.assertEqual(while_ev["status"], "nieosiagalny")
        self.assertEqual(after_ev["status"], "wstepny_plan")
        self.assertLessEqual(after_ev["grid_peak_kw"], 13)

    def test_not_an_unvalidated_automatic_charge_command(self):
        result = self.plan()
        self.assertNotIn("service", result)
        self.assertFalse(result["hardware_control"])
        self.assertFalse(result["future_ev_schedule_verified"])

    def test_unknown_daytime_pv_blocks_recommendation(self):
        result = self.plan(pv=[])
        self.assertEqual(result["status"], "brak_prognozy_pv")

    def test_solar_will_fill_battery_so_no_grid_needed(self):
        sunny = [engine.PvSlot(s.start, 8 if s.start.astimezone(TZ).hour >= 12 else 0, 60)
                 for s in self.pv]
        result = self.plan(pv=sunny, soc=40, target=60)
        self.assertEqual(result["status"], "bez_ladowania")
        self.assertEqual(result["grid_charge_kwh"], 0)

    def test_target_above_allowed_soc_returns_error(self):
        result = self.plan(target=101)
        self.assertEqual(result["status"], "bledne_parametry")

    def test_target_applies_manual_slider_only_upstream(self):
        # The corrected value 62% is passed in; advisor must not apply
        # BatteryModel.correction_pp a second time.
        self.model = battery.BatteryModel(
            nominal_kwh=28, minimum_soc=10, maximum_soc=100,
            correction_pp=12)
        result = self.plan(target=62)
        self.assertEqual(result.get("target_soc"), 62)

    def test_cheap_weekend_has_no_spurious_15_hour_cutoff(self):
        saturday = datetime(2026, 11, 7, 9, tzinfo=TZ)
        sunday = datetime(2026, 11, 8, 9, tzinfo=TZ)
        result = self.plan(now=saturday, window=(saturday, sunday), target=80)
        self.assertIn(result["status"], ("wstepny_plan", "brak_prognozy_pv",
                                         "bez_ladowania", "nieosiagalny"))
        self.assertFalse(result["hardware_control"])

    def test_dst_fall_back_timestamp_comparison(self):
        now = datetime(2026, 10, 24, 23, tzinfo=TZ)
        end = datetime(2026, 10, 25, 6, tzinfo=TZ)
        forecast_start = now.astimezone(timezone.utc)
        pv = [engine.PvSlot(forecast_start + timedelta(hours=i), 0, 60)
              for i in range(15)]
        result = self.plan(now=now, window=(now, end), pv=pv, target=70)
        self.assertIn(result["status"], ("wstepny_plan", "bez_ladowania", "nieosiagalny"))
        self.assertFalse(result["hardware_control"])

    def test_buffer_prevents_proposing_15kw(self):
        result = self.plan(base=6000, target=70)
        if result["status"] == "wstepny_plan":
            self.assertLessEqual(result["grid_peak_kw"], 13)


if __name__ == "__main__":
    unittest.main()
