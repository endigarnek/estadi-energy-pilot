"""Manufacturer-verified model profiles must never turn generic 350A UI into a hard limit."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"estadi_energy_pilot"
PKG="inverter_specs_offline"
package=types.ModuleType(PKG)
package.__path__=[str(ROOT)]
sys.modules[PKG]=package
spec=importlib.util.spec_from_file_location(f"{PKG}.inverter_specs",ROOT/"inverter_specs.py")
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


class SpecsTests(unittest.TestCase):
    def test_exact_15kw_has_280amps_not_350amps(self):
        p=mod.known_model("SUN-15K-SG05LP3-EU-SM2")
        self.assertEqual(p["rated_ac_kw"],15)
        self.assertEqual(p["manufacturer_max_charge_a"],280)
        self.assertEqual(p["manufacturer_max_discharge_a"],280)
        self.assertFalse(p["auto_control_approved"])

    def test_family_20kw_350_is_not_15kw(self):
        p=mod.known_model("SUN-20K-SG05LP3-EU-SM2")
        self.assertEqual(p["manufacturer_max_charge_a"],350)

    def test_only_exact_model_not_generic_deye_or_watt_rating(self):
        for name in (None,"15kW","LV 3-Phase Hybrid Inverter",
                     "SUN-15K-SG04LP5-EU","SUN-15K-SG05LP3-EU"):
            self.assertIsNone(mod.known_model(name))
            comparison=mod.comparison_for_laboratory(name)
            self.assertFalse(comparison["matched_exact_official_model"])
            self.assertIsNone(comparison["matched_datasheet_profile"])
            self.assertTrue(comparison["not_confirmation_of_installed_model"])

    def test_matching_exact_model_explicitly_is_still_not_bms_approval(self):
        result=mod.comparison_for_laboratory("Deye SUN-15K-SG05LP3-EU-SM2")
        self.assertTrue(result["matched_exact_official_model"])
        self.assertFalse(result["matched_datasheet_profile"]["auto_control_approved"])
        self.assertTrue(result["not_a_bms_limit"])
        self.assertIn("deyeinverter.com",result["reference_url"])


if __name__=="__main__":
    unittest.main()
