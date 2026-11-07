"""Regression tests for native Lovelace YAML dashboard export."""
from __future__ import annotations

import ast
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
    "history_status": "sensor.energy_hourly_history",
    "lab_status": "sensor.energy_lab_last",
    "lab_meters": "button.lab_meters",
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
    "source_battery": "sensor.deye_battery_power",
    "source_losses": "sensor.deye_power_losses",
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

    def test_optional_smart_charge_status_does_not_block_export(self):
        """Regression for HA button error reported on 2026-11-06."""
        entities = {k: v for k, v in ENTITIES.items()
                    if k != "smart_charge_status"}
        dashboard = mod.render_dashboard(entities, SOURCES)
        mini = mod.render_mini_widget(entities, SOURCES)
        self.assertIn("views:", dashboard)
        self.assertIn("type: custom:estadi-energy-forecast-card", dashboard)
        self.assertIn("views:", mini)
        self.assertNotIn("sensor.energy_charging_status", dashboard)
        try:
            import yaml
        except ImportError:
            pass
        else:
            self.assertIsInstance(yaml.safe_load(dashboard), dict)

    def test_button_maps_smart_charge_status_to_real_sensor_registry(self):
        """Catch future omissions between sensor.py and button.py."""
        root = SRC.parent
        def tuple_assignment(path, symbol):
            source = ast.parse(path.read_text(encoding="utf-8"))
            for node in source.body:
                if isinstance(node, ast.Assign):
                    if any(isinstance(target, ast.Name) and target.id == symbol
                           for target in node.targets):
                        return ast.literal_eval(node.value)
            raise AssertionError(f"Missing {symbol} in {path}")

        known = tuple_assignment(root / "sensor.py", "ENERGY_V2_SENSORS")
        mapped = tuple_assignment(root / "button.py", "SENSOR_KEYS")
        keys = {name for name, _, _ in known}
        self.assertIn("smart_charge_status", keys)
        self.assertIn("smart_charge_status", mapped)
        self.assertTrue(set(mapped).issubset(keys))
        self.assertEqual(len(mapped), len(set(mapped)))

    def test_smart_charge_sensor_tile_uses_discovered_entity_id(self):
        rendered = mod.render_dashboard(ENTITIES, SOURCES)
        self.assertIn("Inteligentne ładowanie", rendered)
        self.assertIn("sensor.energy_charging_status", rendered)

    def test_interactive_card_uses_actual_simulation_entity(self):
        dashboard = mod.render_dashboard(ENTITIES, SOURCES)
        self.assertIn("type: custom:estadi-energy-forecast-card", dashboard)
        self.assertIn("sensor.energy_simulation", dashboard)
        self.assertIn("default_series:", dashboard)
        self.assertIn("zapasowa tabela 4h", dashboard)

    def test_resource_export_creates_js_once_and_respects_edits(self):
        full = mod.render_dashboard(ENTITIES, SOURCES)
        mini = mod.render_mini_widget(ENTITIES, SOURCES)
        javascript = ("customElements.define('estadi-energy-forecast-card', class extends HTMLElement {});" "customElements.define('estadi-energy-overview-card', class extends HTMLElement {});" "customElements.define('estadi-energy-control-card', class extends HTMLElement {});")
        with TemporaryDirectory() as folder:
            first = mod.export_files(folder, full, mini, javascript)
            self.assertEqual(first["forecast_resource_url"], mod.FORECAST_CARD_RESOURCE)
            self.assertEqual(Path(first["forecast_js"]).parent, Path(folder) / "www")
            self.assertEqual(Path(first["forecast_js"]).read_text(), javascript)
            second = mod.export_files(folder, full, mini, javascript)
            self.assertEqual(second["forecast_js"], first["forecast_js"])
            self.assertEqual(second["dashboard"], first["dashboard"])
            self.assertEqual(second["mini"], first["mini"])
            self.assertFalse(list(Path(folder).glob("estadi-energy-pilot-dashboard-[0-9]*.yaml")))
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

    def test_calibration_and_ev_stress_visible_in_exported_dashboard(self):
        entities = {
            **ENTITIES,
            "calibration_status": "sensor.owner_calibration",
            "calibration_load_mae": "sensor.owner_load_mae",
            "calibration_pv_discount": "sensor.owner_suggested_pv",
            "calibration_ev_status": "sensor.owner_ev_uncertainty",
            "economic_status": "sensor.owner_economics",
        }
        full = mod.render_dashboard(entities, SOURCES)
        self.assertIn("sensor.owner_calibration", full)
        self.assertIn("sensor.owner_ev_uncertainty", full)
        self.assertIn("historyczny_wariant_ryzyka_EV", full)
        self.assertIn("ev_historyczny_scenariusz_stresowy", full)
        self.assertIn("Nie traktuj tego jako prawdopodobieństwa", full)
        self.assertIn("Żadna korekta nie jest stosowana automatycznie", full)

    def test_heat_pump_learned_bands_and_preview_are_in_dashboard(self):
        entries = {
            **ENTITIES,
            "pump_learn_status": "sensor.owner_heat_pump_learning",
            "pump_learn_days": "sensor.owner_heat_pump_days",
            "pump_learn_hours": "sensor.owner_heat_pump_hours",
            "pump_learn_mae": "sensor.owner_heat_pump_mae",
            "pump_preview_learned": "sensor.owner_heat_pump_new",
            "pump_preview_legacy": "sensor.owner_heat_pump_old",
        }
        result = mod.render_dashboard(entries, SOURCES)
        self.assertIn("sensor.owner_heat_pump_learning", result)
        self.assertIn("sensor.owner_heat_pump_new", result)
        self.assertIn("model_wyuczony_w_zakresach", result)
        self.assertIn("porownanie_48h", result)
        self.assertIn("tylko podgląd", result)
        self.assertIn("Temperatura a zużycie pompy", result)

    def test_historical_heat_pump_excess_section_has_no_assumed_cause(self):
        entities = {
            **ENTITIES,
            "pump_excess_status": "sensor.owner_pump_excess",
            "pump_excess_hours": "sensor.owner_pump_evaluated_hours",
            "pump_excess_events": "sensor.owner_pump_periods",
            "pump_excess_kwh": "sensor.owner_extra_kwh",
            "pump_excess_last": "sensor.owner_last_excess",
        }
        out = mod.render_dashboard(entities, SOURCES)
        self.assertIn("sensor.owner_pump_excess", out)
        self.assertIn("sensor.owner_extra_kwh", out)
        self.assertIn("ostatnie_okresy", out)
        self.assertIn("Przyczyna pozostaje nieustalona", out)
        self.assertIn("nie liczymy cykli", out)
        self.assertNotIn("climate.set_temperature", out)

    def test_mini_widget_small_self_contained(self):
        mini = mod.render_mini_widget(ENTITIES, SOURCES)
        self.assertIn("sensor.deye_pv_power", mini)
        self.assertIn("sensor.deye_load_power", mini)
        self.assertIn("type: custom:estadi-energy-overview-card", mini)
        self.assertIn("mode: compact", mini)
        self.assertIn("type: panel", mini)
        self.assertNotIn("harmonogram_48h", mini)
        self.assertNotIn("type: tile", mini)


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

    def test_managed_export_is_idempotent_and_does_not_overwrite_edits(self):
        full = mod.render_dashboard(ENTITIES, SOURCES)
        mini = mod.render_mini_widget(ENTITIES, SOURCES)
        with TemporaryDirectory() as folder:
            legacy = Path(folder) / "estadi-energy-pilot-dashboard.yaml"
            legacy.write_text("ręczne zmiany właściciela", encoding="utf-8")
            a = mod.export_files(folder, full, mini)
            b = mod.export_files(folder, full, mini)
            self.assertEqual(a, b)
            self.assertEqual(legacy.read_text(encoding="utf-8"),
                             "ręczne zmiany właściciela")
            self.assertEqual(Path(a["dashboard"]).read_text(encoding="utf-8"), full)
            self.assertTrue(a["dashboard"].endswith("-managed.yaml"))
            self.assertEqual(len(list(Path(folder).glob("estadi-energy-pilot-dashboard-*.yaml"))), 1)
            self.assertTrue((Path(folder) / ".estadi-energy-pilot-managed.json").is_file())
            Path(a["dashboard"]).write_text("owner edited", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Nie nadpisano"):
                mod.export_files(folder, full, mini)
            self.assertEqual(Path(a["dashboard"]).read_text(), "owner edited")

    def test_managed_export_updates_same_file_when_entity_ids_change(self):
        with TemporaryDirectory() as folder:
            original = mod.export_files(folder, "views:\n  - title: A\n",
                                        "views:\n  - title: Mini\n")
            newer = mod.export_files(folder, "views:\n  - title: B\n",
                                     "views:\n  - title: Mini\n")
            self.assertEqual(newer, original)
            self.assertIn("title: B", Path(newer["dashboard"]).read_text())
            self.assertFalse(list(Path(folder).glob("*-2.yaml")))

    def test_modern_overview_is_live_and_separates_diagnostics(self):
        full = mod.render_dashboard(ENTITIES, SOURCES)
        self.assertIn("custom:estadi-energy-control-card", full)
        self.assertIn("entity_soc: \"sensor.deye_soc_by_owner\"", full)
        self.assertIn("entity_home: \"sensor.deye_load_power\"", full)
        self.assertIn("path: estadi-diagnostyka", full)
        self.assertIn("path: estadi-prognoza", full)
        self.assertNotIn("sensor.nonexistent", full)

    def test_compact_cockpit_uses_actual_source_ids_and_lab(self):
        full = mod.render_dashboard(ENTITIES, SOURCES)
        self.assertIn("custom:estadi-energy-control-card", full)
        self.assertIn("sensor.deye_power_losses", full)
        self.assertIn("sensor.deye_battery_power", full)
        self.assertIn("sensor.energy_hourly_history", full)
        self.assertIn("estadi-testy", full)
        self.assertIn("button.lab_meters", full)
        self.assertIn("perform_action: button.press", full)
        self.assertNotIn("number.set_value", full)

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
        self.assertEqual(len(dashboard["views"]), 6)
        self.assertEqual(dashboard["views"][0]["type"], "panel")
        self.assertEqual(dashboard["views"][0]["cards"][0]["type"],
                         "custom:estadi-energy-control-card")
        self.assertEqual(dashboard["views"][1]["type"], "sections")
        self.assertEqual(dashboard["views"][2]["type"], "sections")
        self.assertEqual(dashboard["views"][4]["path"], "estadi-testy")
        self.assertGreater(len(dashboard["views"][5]["sections"]), 4)
        self.assertTrue(all(section["cards"][0]["type"] == "heading"
                            for view in dashboard["views"][1:]
                            for section in view["sections"]))


if __name__ == "__main__":
    unittest.main()
