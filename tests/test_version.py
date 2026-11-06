"""Check that the user-visible diagnostic version matches manifest.json."""
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "estadi_energy_pilot"


class VersionTests(unittest.TestCase):
    def test_manifest_matches_sensor_version(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        namespace = {}
        exec((ROOT / "const.py").read_text(encoding="utf-8"), namespace)
        self.assertEqual(manifest["version"], namespace["INTEGRATION_VERSION"])


if __name__ == "__main__":
    unittest.main()
