"""Check complete installable archives, including non-game metadata paths."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from converter import package
from settings import FollowerSettings


class PackageTests(unittest.TestCase):
    def test_distinct_mods_have_no_case_insensitive_installed_path_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            packages = []
            for mod_id in ("FirstFollower", "SecondFollower"):
                settings = FollowerSettings(mod_id=mod_id, npc_name=mod_id)
                output = Path(directory) / mod_id
                mod = output / "mod"
                model = mod / "meshes" / settings.asset_dir / "avatar.nif"
                model.parent.mkdir(parents=True)
                model.write_bytes(b"model bytes unchanged")
                plugin = mod / settings.plugin_name
                plugin.write_bytes(b"plugin bytes unchanged")
                # Simulate the actual shared files left by a pre-0.4.1 build.
                (mod / "README.txt").write_text("old generated readme")
                settings.save(mod / "VRM2Skyrim-settings.json")
                before = {path.relative_to(mod).as_posix(): path.read_bytes()
                          for path in (model, plugin)}
                archive = package(output, settings)
                with zipfile.ZipFile(archive) as source:
                    self.assertIsNone(source.testzip())
                    names = source.namelist()
                    self.assertNotIn("README.txt", names)
                    self.assertNotIn("VRM2Skyrim-settings.json", names)
                    prefix = settings.asset_dir + "/"
                    self.assertIn(prefix + "README.txt", names)
                    self.assertIn(prefix + "settings.json", names)
                    restored = FollowerSettings.from_dict(json.loads(source.read(prefix + "settings.json")))
                    self.assertEqual(restored, settings)
                    for name, expected in before.items():
                        self.assertEqual(source.read(name), expected)
                    manifest = json.loads((output / "package-manifest.json").read_text())
                    self.assertEqual(manifest, {name: hashlib.sha256(source.read(name)).hexdigest()
                                                for name in names})
                    packages.append({name.replace("\\", "/").casefold() for name in names})
            self.assertFalse(packages[0] & packages[1])


if __name__ == "__main__":
    unittest.main()
