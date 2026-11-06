"""Regression tests for native Lovelace YAML dashboard export."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

SRC = Path(__file__).resolve().parents[1] / "custom_components/estadi_energy_pilot/dashboard_export.py"
spec = importlib.util.spec_from_file_location("dashboard_export_tests", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ENTITIES = {
    "mini_status": "sensor.energy_status_renamed_by_owner",
    "grid_status": "sensor.energy_grid_status_x",
    "grid_import": "sensor.energy_grid_import_12",
    "grid_headroom": "sensor.energy_headroom",
    "grid_charge_cap": "sensor.energy_charge_cap",
    "sim_status": "sensor.energy_simulation",
    "sim_hours": "sensor.energy_sim_hours",
    "sim_quality": "sensor.energy_sim_quality",
    "smart_charge_status": "sensor.energy_charging_status",
    "dry_run_status": "sensor.energy_dry_run",
    "dry_run_action": "sensor.energy_dry_run_action",
    "dry_run_power": "sensor.energy_dry_run_power",
    "dry_run_days": "sensor.energy_dry_run_days",
    "accuracy_status": "sensor.energy_accuracy",
    "tariff": "sensor.energy_tariff",
    "tariff_zone": "sensor.energy_zone",
    "refresh": "button.owner_refresh_button",
    "version": "sensor.energy_version",
}
SOURCES = {
    "source_soc": "sensor.deye_soc_by_owner",
    "source_pv": "sensor.deye_pv_power",
    "source_home": "sensor.deye_load_power",
    "source_ev": "sensor.moc_ladowarki_poprawna",
    "source_pump": "sensor.shellyem3_08f9e051e0b0_channel_b_power",
}


class DashboardExportTests(unittest.TestCase):
    def test_full_dashboard_contains_real_entity_ids(self):
        dashboard = mod.render_dashboard(ENTITIES, SOURCES)
        self.assertIn("views:", dashboard)
        self.assertIn("type: grid", dashboard)
        self.assertIn("type: history-graph", dashboard)
        self.assertIn("type: markdown", dashboard)
        self.assertIn("sensor.energy_status_renamed_by_owner", dashboard)
        self.assertIn("sensor.deye_load_power", dashboard)
        self.assertIn("sensor.shellyem3_08f9e051e0b0_channel_b_power", dashboard)
        self.assertIn("harmonogram_48h", dashboard)
        self.assertIn("Deye WYŁĄCZONE", dashboard)
        self.assertNotIn("sensor.estadi_energy_pilot_szybki_status", dashboard)

    def test_interactive_card_uses_actual_simulation_entity(self):
        dashboard = mod.render_dashboard(ENTITIES, SOURCES)
        self.assertIn("type: custom:estadi-energy-forecast-card", dashboard)
        self.assertIn("sensor.energy_simulation", dashboard)
        self.assertIn("default_series:", dashboard)
        self.assertIn("zapasowa tabela 4h", dashboard)

    def test_resource_export_creates_js_once_and_respects_edits(self):
        full = mod.render_dashboard(ENTITIES, SOURCES)
        mini = mod.render_mini_widget(ENTITIES, SOURCES)
        javascript = "customElements.define('estadi-energy-forecast-card', class extends HTMLElement {});"
        with TemporaryDirectory() as folder:
            first = mod.export_files(folder, full, mini, javascript)
            self.assertEqual(first["forecast_resource_url"], mod.FORECAST_CARD_RESOURCE)
            self.assertEqual(Path(first["forecast_js"]).parent, Path(folder) / "www")
            self.assertEqual(Path(first["forecast_js"]).read_text(), javascript)
            second = mod.export_files(folder, full, mini, javascript)
            self.assertEqual(second["forecast_js"], first["forecast_js"])
            self.assertNotEqual(second["dashboard"], first["dashboard"])
            Path(first["forecast_js"]).write_text("owner-custom", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Nie nadpisano"):
                mod.export_files(folder, full, mini, javascript)
            self.assertEqual(Path(first["forecast_js"]).read_text(), "owner-custom")

    def test_reject_invalid_card_asset_without_exporting_yaml(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Nieprawidłowy"):
                mod.export_files(folder, "views:\\n", "views:\\n", "console.log('bad')")
            self.assertFalse(list(Path(folder).glob("*.yaml")))

    def test_economy_card_explains_costs_and_terminal_soc(self):
        entities = {**ENTITIES,
                    "economic_status": "sensor.energy_economy_status",
                    "economic_base_cost": "sensor.energy_base_import_cost",
                    "economic_plan_cost": "sensor.energy_plan_import_cost",
                    "economic_base_soc": "sensor.energy_base_soc",
                    "economic_plan_soc": "sensor.energy_plan_soc"}
        dashboard = mod.render_dashboard(entities, SOURCES)
        self.assertIn("sensor.energy_economy_status", dashboard)
        self.assertIn("Rachunek dwóch scenariuszy 48h", dashboard)
        self.assertIn("scenariusz_bez_ladowania", dashboard)
        self.assertIn("Końcowy SOC", dashboard)
        self.assertIn("nie rzeczywiste oszczędności", dashboard)
        self.assertIn("type: custom:estadi-energy-forecast-card", dashboard)

    def test_mini_widget_small_self_contained(self):
        mini = mod.render_mini_widget(ENTITIES, SOURCES)
        self.assertIn("sensor.energy_status_renamed_by_owner", mini)
        self.assertIn("sensor.energy_dry_run_action", mini)
        self.assertIn("sensor.deye_pv_power", mini)
        self.assertIn("type: tile", mini)
        self.assertIn("sterowanie Deye wyłączone", mini)
        self.assertNotIn("harmonogram_48h", mini)

    def test_missing_core_entities_fail_without_fake_ids(self):
        with self.assertRaisesRegex(ValueError, "sim_status"):
            mod.render_dashboard({k:v for k,v in ENTITIES.items() if k != "sim_status"}, SOURCES)
        with self.assertRaisesRegex(ValueError, "Szybki status"):
            mod.render_mini_widget({}, SOURCES)

    def test_partial_external_sensor_list_is_safe(self):
        out = mod.render_dashboard(ENTITIES, {})
        self.assertIn("Brak skonfigurowanych czujników dla wykresu", out)
        self.assertNotIn("sensor.deye_load_power", out)

    def test_yaml_strings_escaped_for_custom_entity_names(self):
        ids = {**ENTITIES, "grid_status": 'sensor.owner_q\\"ue'}
        yaml = mod.render_dashboard(ids, {})
        self.assertIn('sensor.owner_q', yaml)
        self.assertNotIn("None", yaml)

    def test_export_does_not_overwrite_existing_files(self):
        full = mod.render_dashboard(ENTITIES, SOURCES)
        mini = mod.render_mini_widget(ENTITIES, SOURCES)
        with TemporaryDirectory() as folder:
            a = mod.export_files(folder, full, mini)
            self.assertEqual(Path(a["dashboard"]).read_text(encoding="utf-8"), full)
            self.assertEqual(Path(a["mini"]).read_text(encoding="utf-8"), mini)
            Path(a["dashboard"]).write_text("owner edited", encoding="utf-8")
            b = mod.export_files(folder, full, mini)
            self.assertNotEqual(a["dashboard"], b["dashboard"])
            self.assertTrue(b["dashboard"].endswith("-2.yaml"))
            self.assertTrue(b["mini"].endswith("-2.yaml"))
            self.assertEqual(Path(a["dashboard"]).read_text(), "owner edited")

    def test_path_is_configuration_dir_not_www_or_integration_dir(self):
        with TemporaryDirectory() as folder:
            paths = mod.export_files(folder, "views:\n", "views:\n")
            for value in paths.values():
                self.assertEqual(Path(value).parent, Path(folder))
                self.assertTrue(value.endswith(".yaml"))

    def test_no_inverter_write_action_is_embedded_in_dashboard(self):
        config = mod.render_dashboard(ENTITIES, SOURCES)
        forbidden = ["number.set_value", "select.select_option",
                     "switch.turn_on", "time.set_value", "script.turn_on"]
        for name in forbidden:
            self.assertNotIn(name, config)
        self.assertIn("automatyczne sterowanie Deye WYŁĄCZONE", config)

    def test_valid_lovelace_yaml_if_pyyaml_is_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is optional in CI; HA has it installed")
        dashboard = yaml.safe_load(mod.render_dashboard(ENTITIES, SOURCES))
        mini = yaml.safe_load(mod.render_mini_widget(ENTITIES, SOURCES))
        self.assertEqual(dashboard["views"][0]["path"], "estadi-energia")
        self.assertEqual(mini["views"][0]["path"], "estadi-mini")
        self.assertGreater(len(dashboard["views"][0]["cards"]), 7)


if __name__ == "__main__":
    unittest.main()
