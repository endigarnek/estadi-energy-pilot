"""Offline regressions of read-only dry-run and persistent decision logging."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

TARGET = (Path(__file__).resolve().parents[1]
          / "custom_components/estadi_energy_pilot/dry_run.py")
spec = importlib.util.spec_from_file_location("estadi_dry_run_tests", TARGET)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

TZ = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 11, 6, 13, 30, tzinfo=TZ)


def baseline(**overrides):
    start = datetime(2026, 11, 6, 13, 15, tzinfo=TZ)
    end = datetime(2026, 11, 6, 15, tzinfo=TZ)
    values = {
        "now": NOW,
        "plan": {"status": "wstepny_plan", "start": start.isoformat(),
                 "end_window": end.isoformat(), "target_soc": 80, "power_kw": 5},
        "grid": {"state": "zapas", "allowed_charge_kw": 4, "phase_checked": True,
                 "import_kw": 9, "current_charge_kw": 1},
        "tou": {"status": "odczytano_6_programow"},
        "soc": 40, "ev_kw": 6.9, "tariff_band": "cheap",
        "plan_computed_at": NOW.isoformat(),
    }
    values.update(overrides)
    return module.evaluate_dry_run(**values)


class DryRunTests(unittest.TestCase):
    def test_hypothetical_four_kw_but_never_sends_command(self):
        result = baseline()
        self.assertEqual(result["status"], "blokada")
        self.assertEqual(result["suggested_kw"], 4)
        self.assertEqual(result["requested_kw"], 5)
        self.assertEqual(result["hipotetyczna_akcja"], "laduj_z_ograniczeniem")
        self.assertFalse(result["control_enabled"])
        self.assertEqual(result["commands_sent"], 0)
        self.assertTrue(result["blockers"])

    def test_car_finishes_more_power_available_but_no_write(self):
        before = baseline()
        after = baseline(grid={
            "state": "zapas", "allowed_charge_kw": 10, "phase_checked": True,
            "import_kw": 3, "current_charge_kw": 0
        }, ev_kw=0)
        self.assertGreater(after["suggested_kw"], before["suggested_kw"])
        self.assertEqual(after["suggested_kw"], 5)
        self.assertEqual(after["commands_sent"], 0)

    def test_outside_cheap_tariff_would_not_charge(self):
        result = baseline(tariff_band="peak")
        self.assertEqual(result["hipotetyczna_akcja"], "poza_tania_taryfa")
        self.assertEqual(result["suggested_kw"], 0)

    def test_before_window_is_waiting_even_with_current_headroom(self):
        early = datetime(2026, 11, 6, 12, 0, tzinfo=TZ)
        result = baseline(now=early, plan_computed_at=early.isoformat())
        self.assertEqual(result["hipotetyczna_akcja"], "czekaj")
        self.assertEqual(result["suggested_kw"], 0)

    def test_goal_reached_means_no_grid_charge(self):
        result = baseline(soc=81)
        self.assertEqual(result["hipotetyczna_akcja"], "cel_osiagniety")
        self.assertEqual(result["suggested_kw"], 0)

    def test_unknown_grid_sign_blocks_and_no_proposed_kw(self):
        result = baseline(grid={"state": "blokada", "allowed_charge_kw": None,
                                "phase_checked": False})
        self.assertIsNone(result["suggested_kw"])
        self.assertIn("Grid Guard", result["why"])

    def test_stale_plan_is_blocked(self):
        old = (NOW - timedelta(minutes=50)).isoformat()
        result = baseline(plan_computed_at=old)
        self.assertEqual(result["code"], "SAFETY_BLOCKERS")
        self.assertTrue(any("35 minut" in block for block in result["blockers"]))

    def test_partial_tou_and_unverified_phases_are_visible(self):
        result = baseline(
            tou={"status": "niekompletne"},
            grid={"state": "zapas", "allowed_charge_kw": 5,
                  "phase_checked": False},
        )
        self.assertGreaterEqual(len(result["blockers"]), 3)
        self.assertEqual(result["commands_sent"], 0)

    def test_missing_plan_does_not_generate_fake_action(self):
        result = baseline(plan={"status": "brak_celu"}, soc=None)
        self.assertIsNone(result["hipotetyczna_akcja"])
        self.assertIsNone(result["suggested_kw"])
        self.assertFalse(result["control_enabled"])

    def test_journal_samples_at_most_every_quarter_until_change(self):
        first = baseline()
        journal = module.DryRunJournal()
        self.assertTrue(journal.observe(first))
        self.assertFalse(journal.observe({**first, "at": (NOW + timedelta(seconds=15)).isoformat()}))
        other = baseline(ev_kw=0, grid={"state": "zapas",
                                         "allowed_charge_kw": 10,
                                         "phase_checked": True})
        other["at"] = (NOW + timedelta(seconds=30)).isoformat()
        self.assertTrue(journal.observe(other))
        self.assertEqual(len(journal.records), 2)
        restored = module.DryRunJournal(journal.export())
        self.assertEqual(restored.report()["zapisanych_decyzji"], 2)
        self.assertEqual(restored.report()["komendy_wyslane"], 0)

    def test_many_transitions_in_one_hour_do_not_count_as_one_full_day(self):
        journal = module.DryRunJournal()
        for i in range(100):
            event = baseline()
            event["at"] = (NOW + timedelta(seconds=15*i)).isoformat()
            event["code"] = "TEST" + str(i)
            journal.observe(event)
        self.assertEqual(journal.report()["pelnych_dni_testu"], 0)

    def test_seven_distinct_full_days_count_without_auto_arming(self):
        journal = module.DryRunJournal()
        for day in range(7):
            for slot in range(96):
                at = (NOW + timedelta(days=day, minutes=15*slot))
                event = baseline()
                event["at"] = at.isoformat()
                journal.observe(event, force=True)
        report = journal.report()
        self.assertGreaterEqual(report["pelnych_dni_testu"], 6)
        self.assertLessEqual(report["pelnych_dni_testu"], 7)
        self.assertFalse(report["gotowosc_sterowania"])
        self.assertEqual(report["komendy_wyslane"], 0)

    def test_no_software_write_api_in_dryrun(self):
        content = TARGET.read_text()
        for forbidden in ("async_call(", "set_value(", "turn_on(", "select_option("):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
