"""Pure regression tests for the read-only Deye TOU inventory."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

TARGET = (Path(__file__).resolve().parents[1] /
          "custom_components/estadi_energy_pilot/deye_tou.py")
spec = importlib.util.spec_from_file_location("estadi_deye_tou_tests", TARGET)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


def state(entity_id, value, unit=None):
    attrs = {} if unit is None else {"unit_of_measurement": unit}
    return SimpleNamespace(entity_id=entity_id, state=str(value), attributes=attrs)


def six_slots():
    output = [state("select.deye_time_of_use", "Enabled")]
    for i in range(1, 7):
        output.extend([
            state(f"time.deye_program_{i}_time", f"{i+10:02}:00:00"),
            state(f"number.deye_program_{i}_soc", 70 + i, "%"),
            state(f"number.deye_program_{i}_power", 5000, "W"),
            state(f"select.deye_program_{i}_charging", "Grid"),
        ])
    return output


class TouTests(unittest.TestCase):
    def test_all_six_slots_detected_without_commands(self):
        result = module.inspect_tou(six_slots(), NOW)
        self.assertEqual(result["status"], "odczytano_6_programow")
        self.assertEqual(result["odczytane_pola"], 24)
        self.assertEqual(len(result["programy"]), 6)
        self.assertEqual(result["programy"][0]["power"]["wartosc"], "5.000 kW")
        self.assertEqual(result["programy"][0]["time"]["wartosc"], "11:00")
        self.assertEqual(result["stan_globalny"]["select.deye_time_of_use"], "Enabled")
        self.assertFalse(result["automatyzacja_gotowa"])
        self.assertTrue(result["odczyt_bez_zapisu"])

    def test_missing_one_field_is_partial_no_snapshot(self):
        items = [x for x in six_slots() if x.entity_id != "time.deye_program_3_time"]
        result = module.inspect_tou(items, NOW)
        self.assertEqual(result["status"], "niekompletne")
        self.assertEqual(result["brakujace_pola"], 1)
        self.assertIsNone(module.snapshot_config(result))

    def test_ambiguous_duplicate_sensor_and_number_is_not_guessed(self):
        items = six_slots() + [state("sensor.deye_program_1_soc", 78, "%")]
        result = module.inspect_tou(items, NOW)
        self.assertEqual(result["niejednoznaczne_pola"], 1)
        self.assertEqual(result["programy"][0]["soc"]["status"], "niejednoznaczne")
        self.assertFalse(result["automatyzacja_gotowa"])

    def test_power_percentage_is_never_mistaken_for_kilowatts(self):
        items = six_slots()
        for index, entry in enumerate(items):
            if entry.entity_id == "number.deye_program_2_power":
                items[index] = state(entry.entity_id, 70, "%")
        result = module.inspect_tou(items, NOW)
        self.assertEqual(result["programy"][1]["power"]["wartosc"], "70 %")
        self.assertEqual(result["status"], "odczytano_6_programow")

    def test_invalid_soc_and_power_units_are_rejected(self):
        items = six_slots()
        for index, entry in enumerate(items):
            if entry.entity_id == "number.deye_program_1_soc":
                items[index] = state(entry.entity_id, 105, "%")
            if entry.entity_id == "number.deye_program_2_power":
                items[index] = state(entry.entity_id, 10, "A")
        result = module.inspect_tou(items, NOW)
        self.assertEqual(result["programy"][0]["soc"]["status"], "nieprawidlowy_soc")
        self.assertEqual(result["programy"][1]["power"]["status"],
                         "niepotwierdzona_jednostka_mocy")
        self.assertNotEqual(result["status"], "odczytano_6_programow")

    def test_unrecognized_tou_names_are_suggested_not_assumed(self):
        items = [
            state("number.deye_program_1_charge_current", 20, "A"),
            state("select.deye_weird_tou_mode", "Grid"),
        ]
        result = module.inspect_tou(items, NOW)
        self.assertEqual(result["status"], "nie_wykryto")
        self.assertIn("number.deye_program_1_charge_current",
                      result["inne_mozliwe_encje"])
        self.assertFalse(result["automatyzacja_gotowa"])

    def test_no_device_entities_asks_for_mapping_not_guessing(self):
        result = module.inspect_tou([state("sensor.deye_load_power", 400, "W")], NOW)
        self.assertEqual(result["status"], "nie_wykryto")
        self.assertEqual(result["odczytane_pola"], 0)
        self.assertIsNone(module.snapshot_config(result))

    def test_snapshot_and_readback_diff_does_not_restore(self):
        initial = module.inspect_tou(six_slots(), NOW)
        snapshot = module.snapshot_config(initial)
        self.assertEqual(module.changed_fields(snapshot, initial), [])
        changed = six_slots()
        for index, entry in enumerate(changed):
            if entry.entity_id == "number.deye_program_1_soc":
                changed[index] = state(entry.entity_id, 82, "%")
        new = module.inspect_tou(changed, NOW)
        diffs = module.changed_fields(snapshot, new)
        self.assertEqual(len(diffs), 1)
        self.assertIn("71.0 → 82.0", diffs[0])
        self.assertFalse(new["automatyzacja_gotowa"])

    def test_alternate_time_of_use_names_work(self):
        items = [
            state("time.deye_time_of_use_1_start_time", "20:30"),
            state("number.deye_time_of_use_1_target_soc", 60, "%"),
            state("number.deye_time_of_use_1_charging_power", 7, "kW"),
            state("switch.deye_time_of_use_1_grid_charge", "on"),
        ]
        result = module.inspect_tou(items, NOW)
        self.assertEqual(result["programy"][0]["time"]["wartosc"], "20:30")
        self.assertEqual(result["programy"][0]["power"]["wartosc"], "7.000 kW")
        self.assertEqual(result["status"], "niekompletne")


if __name__ == "__main__":
    unittest.main()
