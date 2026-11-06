"""Offline regression tests: tariffs, SOC inventory, EV, PV and grid limits."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"
PACKAGE = "pilot_economics_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg


def load(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


battery = load("battery_model")
engine = load("engine")
tariffs = load("tariffs")
simulation = load("simulation_48h")
economics = load("scenario_economics")
TZ = ZoneInfo("Europe/Warsaw")


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 12, tzinfo=TZ)
        self.model = battery.BatteryModel(nominal_kwh=28, minimum_soc=10, maximum_soc=100)
        self.pv = [engine.PvSlot(
            self.now.astimezone(timezone.utc) + timedelta(hours=i), 0., 60
        ) for i in range(49)]
        self.plan = {
            "status": "wstepny_plan",
            "start": datetime(2026, 11, 6, 13, tzinfo=TZ).isoformat(),
            "end_window": datetime(2026, 11, 6, 15, tzinfo=TZ).isoformat(),
            "power_kw": 5., "target_soc": 85.,
        }
        self.prices = {"cheap": .45, "peak": 1.10}

    def run_compare(self, *, plan="default", pv=None, soc=20, base_w=1200,
                    export_value=None, prices="default", **kwargs):
        candidate = self.plan if plan == "default" else plan
        prices = self.prices if prices == "default" else prices
        values = dict(
            now=self.now, pv_slots=self.pv if pv is None else pv,
            temperatures=[], learning={"baseline_ready": False},
            model=self.model, soc=soc, current_temp=10,
            tariff="G12w", prices=prices, proposed_plan=candidate,
            export_value_pln_kwh=export_value,
            baseload_w=base_w, mild_w=0, cold_w=0,
            pv_discount_pct=0, efficiency_pct=90,
            battery_max_kw=10, grid_limit_kw=15,
            grid_buffer_kw=2, ev_now_kw=0,
        )
        values.update(kwargs)
        return economics.compare_scenarios(**values)

    def test_same_input_two_scenarios_different_cost_and_soc(self):
        result = self.run_compare(export_value=.30, base_w=100)
        self.assertEqual(result["status"], "rozny_soc_koncowy")
        self.assertGreater(result["plan"]["grid_battery_kwh"], 0)
        self.assertEqual(result["baseline"]["grid_battery_kwh"], 0)
        self.assertGreater(result["plan"]["import_cost_pln"],
                           result["baseline"]["import_cost_pln"])
        self.assertGreater(result["plan"]["soc_end_pct"], result["baseline"]["soc_end_pct"])
        self.assertIsNone(result["estimated_balance_advantage_pln"])
        self.assertIsNone(result["savings_pln"])
        self.assertFalse(result["plan_written_to_deye"])

    def test_missing_export_compensation_not_zero_credit(self):
        result = self.run_compare(export_value=None)
        self.assertEqual(result["status"], "brak_wartosci_eksportu")
        self.assertIsNone(result["baseline"]["export_credit_pln"])
        self.assertIsNone(result["plan"]["estimated_energy_balance_pln"])
        self.assertIsNone(result["estimated_balance_advantage_pln"])
        self.assertIsNotNone(result["import_cost_delta_pln"])

    def test_import_price_absent_never_invents_price(self):
        result = self.run_compare(prices=None, export_value=.4)
        self.assertEqual(result["status"], "brak_cen_importu")
        self.assertIsNone(result["baseline"]["import_cost_pln"])
        self.assertIsNone(result["import_cost_delta_pln"])
        self.assertIsNone(result["savings_pln"])

    def test_no_plan_keeps_baseline_read_only(self):
        result = self.run_compare(plan={"status": "brak_celu"})
        self.assertEqual(result["status"], "brak_planu")
        self.assertIsNone(result["plan"])
        self.assertEqual(result["baseline"]["status"], "gotowy")
        self.assertEqual(result["baseline"]["hours"], 48)

    def test_power_clipped_to_soft_cap_with_no_redispatch(self):
        result = self.run_compare(soc=10, base_w=12000, export_value=.2)
        self.assertEqual(result["baseline"]["status"], "gotowy")
        self.assertLessEqual(result["plan"]["grid_peak_kw"], 13 + 0.01)
        self.assertGreater(result["plan"]["grid_charge_clipped_steps"], 0)
        self.assertEqual(result["plan"]["grid_over_limit_steps"], 0)
        self.assertGreater(result["plan"]["grid_battery_kwh"], 0)

    def test_active_ev_is_counted_only_once_in_first_quarter(self):
        result = self.run_compare(soc=10, base_w=0, ev_now_kw=6.9,
                                  export_value=.3)
        self.assertAlmostEqual(result["baseline"]["ev_kwh"], 1.725, places=2)
        self.assertAlmostEqual(result["plan"]["ev_kwh"], 1.725, places=2)
        self.assertEqual(result["baseline"]["home_kwh"], result["plan"]["home_kwh"])
        self.assertTrue(result["future_ev_unknown"])

    def test_solar_surplus_can_charge_pv_or_export_not_both_twice(self):
        sunny = []
        for i, row in enumerate(self.pv):
            watts = 6 if 6 <= i <= 10 else 0
            sunny.append(engine.PvSlot(row.start, watts, 60))
        result = self.run_compare(pv=sunny, soc=90, base_w=1000, export_value=.3)
        self.assertEqual(result["baseline"]["status"], "gotowy")
        self.assertGreater(result["baseline"]["export_kwh"], 0)
        self.assertGreater(result["baseline"]["pv_kwh"], 0)
        # PV first serves the home; only the remainder can charge/export.
        self.assertLessEqual(result["baseline"]["export_kwh"],
                             result["baseline"]["pv_kwh"])
        self.assertEqual(result["baseline"]["ev_kwh"], 0)

    def test_daytime_pv_data_missing_blocks_cost_comparison(self):
        result = self.run_compare(pv=self.pv[:2], export_value=.3)
        self.assertEqual(result["status"], "niepelna_prognoza")
        self.assertLess(result["horizon_h"], 48)
        self.assertIsNone(result["import_cost_delta_pln"])
        self.assertIsNone(result["baseline"]["import_cost_pln"])

    def test_no_forecast_yields_no_fake_scenario(self):
        result = self.run_compare(pv=[])
        self.assertEqual(result["status"], "brak_prognozy_pv")
        self.assertNotIn("baseline", result)
        self.assertIsNone(result["savings_pln"])

    def test_equal_terminal_soc_can_produce_only_an_estimate(self):
        # Heavy overnight usage depletes BOTH variants to their SOC minimum.
        result = self.run_compare(base_w=4000, soc=10, export_value=.2)
        self.assertEqual(result["status"], "porownanie_wstepne")
        self.assertAlmostEqual(result["terminal_soc_difference_pp"], 0, places=1)
        self.assertIsNotNone(result["estimated_balance_advantage_pln"])
        self.assertIsNone(result["realized_savings_pln"])

    def test_tariff_prices_apply_to_real_date_and_zone(self):
        cheap_start = datetime(2026, 11, 6, 13, tzinfo=TZ)
        self.assertEqual(tariffs.tariff_zone(cheap_start, "G12w"), "cheap")
        result = self.run_compare(base_w=3000, soc=10, export_value=.2)
        self.assertGreater(result["baseline"]["import_cost_pln"], 0)

    def test_invalid_plan_rejected_no_unsafe_recommendation(self):
        broken = dict(self.plan, power_kw=40)
        result = self.run_compare(plan=broken)
        self.assertEqual(result["status"], "bledny_plan")
        self.assertIsNone(result["savings_pln"])
        self.assertFalse(result["plan_written_to_deye"])

    def test_no_charging_on_expensive_zone(self):
        p = dict(self.plan,
                 start=datetime(2026, 11, 6, 15, tzinfo=TZ).isoformat(),
                 end_window=datetime(2026, 11, 6, 17, tzinfo=TZ).isoformat())
        result = self.run_compare(plan=p, soc=10, base_w=0)
        self.assertAlmostEqual(result["plan"]["grid_battery_kwh"], 0, places=2)

    def test_dst_48h_is_elapsed_not_local_wall_clock(self):
        now = datetime(2026, 10, 24, 23, tzinfo=TZ)
        forecast = [engine.PvSlot(now.astimezone(timezone.utc) +
                                  timedelta(hours=i), 0, 60) for i in range(49)]
        result = self.run_compare(now=now, pv=forecast, plan=None)
        self.assertEqual(result["baseline"]["hours"], 48)
        self.assertEqual(result["baseline"]["status"], "gotowy")

    def test_ev_stress_is_separate_and_never_sent_to_inverter(self):
        ev_schedule = [0.] * 24
        ev_schedule[17] = 7.
        ev_schedule[18] = 7.
        risk = {
            "risk_ready": True,
            "profiles": {
                "weekday": {"p90_kwh_per_hour": ev_schedule},
                "weekend": {"p90_kwh_per_hour": ev_schedule},
            },
            "warning": "To tylko historyczny wariant stresowy, nie pewna sesja EV",
        }
        result = self.run_compare(
            soc=10, base_w=1000, export_value=.2,
            future_ev_stress=risk,
        )
        stress = result["ev_stress"]
        self.assertIsNotNone(stress)
        self.assertEqual(stress["status"], "gotowy_scenariusz_stresowy")
        self.assertGreater(stress["baseline"]["ev_kwh"], result["baseline"]["ev_kwh"])
        self.assertGreater(stress["plan"]["ev_kwh"], result["plan"]["ev_kwh"])
        self.assertGreaterEqual(
            stress["plan"]["import_cost_pln"],
            result["plan"]["import_cost_pln"],
        )
        self.assertIsNone(stress["estimated_savings_pln"])
        self.assertFalse(stress["future_ev_sessions_confirmed"])
        self.assertFalse(result["plan_written_to_deye"])

    def test_ev_history_without_seven_complete_days_cannot_invent_plan(self):
        risk = {"risk_ready": False, "profiles": {}, "warning": "Brak pomiarów"}
        result = self.run_compare(future_ev_stress=risk)
        self.assertIsNone(result["ev_stress"])
        self.assertTrue(result["future_ev_unknown"])

    def test_active_car_is_not_counted_twice_at_start_of_stress(self):
        ev_schedule = [0.] * 24
        ev_schedule[self.now.hour] = 8.  # 12:00 is currently active
        risk = {
            "risk_ready": True,
            "profiles": {
                "weekday": {"p90_kwh_per_hour": ev_schedule},
                "weekend": {"p90_kwh_per_hour": ev_schedule},
            },
        }
        result = self.run_compare(
            soc=10, base_w=0, ev_now_kw=6.9, future_ev_stress=risk,
        )
        # First 15min uses the real 6.9 kW reading, not historical 8 kW.
        # Remaining 45min of 12:00 may follow the stress EV profile.
        self.assertAlmostEqual(result["baseline"]["ev_kwh"], 1.725, places=2)
        self.assertGreater(result["ev_stress"]["baseline"]["ev_kwh"], 1.725)
        self.assertFalse(result["plan_written_to_deye"])

    def test_costs_do_not_show_up_as_realized_savings(self):
        result = self.run_compare(export_value=.3)
        self.assertIsNone(result["savings_pln"])
        self.assertIsNone(result["realized_savings_pln"])
        self.assertTrue(result["phase_safety_not_verified"])


if __name__ == "__main__":
    unittest.main()
