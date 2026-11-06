"""Safe HACS/Marketplace update blueprint: only chosen update entity is targeted."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "blueprints/estadi_energy_pilot_auto_update.yaml"


class UpdateBlueprintTests(unittest.TestCase):
    def test_update_blueprint_is_narrow_and_opt_in(self):
        import yaml

        class Loader(yaml.SafeLoader):
            pass

        Loader.add_constructor("!input", lambda loader, node: {
            "input": loader.construct_scalar(node)
        })

        content = SOURCE.read_text(encoding="utf-8")
        data = yaml.load(content, Loader=Loader)
        self.assertEqual(data["blueprint"]["domain"], "automation")
        self.assertIn("main/blueprints/estadi_energy_pilot_auto_update.yaml",
                      data["blueprint"]["source_url"])
        self.assertEqual(data["blueprint"]["input"]["restart_after_install"]["default"], False)
        self.assertEqual(data["blueprint"]["input"]["update_time"]["default"], "03:45:00")

        actions = data["actions"]
        self.assertEqual(actions[0]["action"], "update.install")
        self.assertEqual(actions[0]["target"]["entity_id"], {"input": "estadi_update"})
        self.assertEqual(data["conditions"][0]["entity_id"], {"input": "estadi_update"})
        self.assertEqual(data["conditions"][0]["state"], "on")
        self.assertEqual(actions[1]["continue_on_timeout"], False)
        self.assertEqual(actions[1]["timeout"], "00:20:00")
        self.assertEqual(actions[2]["then"][0]["action"], "homeassistant.restart")

        forbidden = ("hassio.update", "climate.set", "number.set_value",
                     "switch.turn_on", "shell_command", "command_line")
        for command in forbidden:
            self.assertNotIn(command, content)


if __name__ == "__main__":
    unittest.main()
