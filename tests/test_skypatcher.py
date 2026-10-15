"""Independent armor export, native plugin references and runtime prerequisites."""

import json
from pathlib import Path
import struct
import tempfile
import unittest

from follower_plugin import follower_records, write_follower
from plugin import Record, records
from skypatcher import (
    config_paths,
    installation_status,
    rules,
    write_registration,
    validate_registration,
)
from settings import FollowerSettings
from converter import package


def profile(plugin):
    return {
        "plugin": plugin,
        "equipment": [
            dict(
                origin_plugin="Skyrim.esm",
                origin_local_id=0x123,
                original_form_id=0x123,
                addon_local_id=0x1000,
                editor_id="Boots",
                hide_hair=True,
            ),
            dict(
                origin_plugin="Dragonborn.esm",
                origin_local_id=0x456,
                original_form_id=0x04000456,
                addon_local_id=0x1001,
                editor_id="Helmet",
                hide_face=True,
            ),
        ],
    }


class SkyPatcherTests(unittest.TestCase):
    def test_rules_are_guarded_relative_additive_and_independent(self):
        a, b = rules(profile("First.esp")), rules(profile("Second.esp"))
        self.assertEqual(len(a["armor"]), 2)
        for line in a["armor"]:
            self.assertIn("hasPlugins=First.esp,", line)
            self.assertIn("filterByArmorAddonsExcluded=First.esp|", line)
            self.assertNotIn("Second.esp", line)
            self.assertNotIn("clearArmorAddons", line)
        self.assertIn("Dragonborn.esm|000456", "\n".join(a["armor"]))
        self.assertTrue(all("Second.esp|" in line for line in b["armor"]))
        self.assertFalse(
            set(config_paths("First.esp").values())
            & set(config_paths("Second.esp").values())
        )
        duplicate = profile("First.esp")
        duplicate["equipment"] *= 2
        self.assertEqual(rules(duplicate), a)

        # Simulate the supported append rules by plugin-relative identity. No
        # scanner or aggregate artifact has to be rebuilt as plugins change.
        def register(enabled):
            items = {
                "Skyrim.esm|000123": ["OriginalRaceAA"],
                "Dragonborn.esm|000456": ["OriginalRaceAA"],
            }
            for generated in [a, b]:
                for line in generated["armor"]:
                    fields = dict(part.split("=", 1) for part in line.split(":"))
                    if not set(fields["hasPlugins"].split(",")) <= enabled:
                        continue
                    target = items[fields["filterByArmors"]]
                    addon = fields["armorAddonsToAdd"]
                    if fields["filterByArmorAddonsExcluded"] not in target:
                        target.append(addon)
            return items

        for enabled in [
            set(),
            {"First.esp"},
            {"Second.esp"},
            {"First.esp", "Second.esp"},
        ]:
            result = register(enabled | {"Skyrim.esm", "Dragonborn.esm"})
            for addons in result.values():
                self.assertEqual(len(addons), 1 + len(enabled))

    def test_follower_official_masters_remap_all_private_links_and_preserve_payloads(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "Test.esp"
            items = [
                Record(
                    b"RACE", 0x01000804, 0, [(b"WNAM", struct.pack("<I", 0x01000801))]
                ),
                Record(
                    b"NPC_",
                    0x01000800,
                    0,
                    [
                        (tag, struct.pack("<I", n))
                        for tag, n in [
                            (b"RNAM", 0x01000804),
                            (b"WNAM", 0x01000801),
                            (b"DOFT", 0x01000803),
                            (b"PNAM", 0x0100080C),
                            (b"ZNAM", 0x01000880),
                        ]
                    ],
                ),
                Record(
                    b"ARMA",
                    0x01001000,
                    0,
                    [
                        (b"RNAM", struct.pack("<I", 0x01000804)),
                        (b"SNDD", struct.pack("<I", 0x02001234)),
                    ],
                ),
                Record(
                    b"RELA",
                    0x01000805,
                    0,
                    [(b"DATA", struct.pack("<IIHBBI", 0x01000800, 7, 1, 0, 0, 0))],
                ),
            ]
            cell = Record(
                b"CELL",
                0x165A7,
                0,
                [],
                ((b"CELL", 0), (struct.pack("<i", 7), 2), (struct.pack("<i", 1), 3)),
            )
            actor = Record(
                b"ACHR", 0x01000806, 0x400, [(b"NAME", struct.pack("<I", 0x01000800))]
            )
            write_follower(
                p,
                items,
                author="test",
                placement=(cell, actor),
                extra_masters=["Dragonborn.esm"],
            )
            disk = list(records(p))
            npc = next(r for r in disk if r.kind == b"NPC_")
            self.assertEqual(npc.form_id, 0x02000800)
            self.assertEqual(npc.values(b"ZNAM"), [struct.pack("<I", 0x02000880)])
            addon = next(r for r in disk if r.kind == b"ARMA")
            self.assertEqual(addon.values(b"SNDD"), [struct.pack("<I", 0x01001234)])
            canonical = {r.form_id: r for r in follower_records(p)}
            for original in items:
                self.assertEqual(canonical[original.form_id].fields, original.fields)
            ref = next(r for r in canonical.values() if r.kind == b"ACHR")
            self.assertEqual(ref.values(b"NAME"), [struct.pack("<I", 0x01000800)])

    def test_exported_zip_owns_only_its_registration_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            s = FollowerSettings(
                mod_id="Independent",
                armor_support=True,
                fit_armors=["ArmorIronBoots"],
                appearance_source_sha256="a" * 64,
                appearance_parts={
                    "body": [1],
                    "underwear": [2],
                    "fixed": [3],
                    "garments": [
                        dict(
                            id="coat",
                            name="coat",
                            nodes=[4],
                            slot=44,
                            armor_type="clothing",
                            armor_rating=0,
                            weight=1,
                            value=1,
                            equipped=True,
                        )
                    ],
                },
            )
            s.save(output / "settings.json")
            prof = profile(s.plugin_name)
            (output / "armor-fitting.json").write_text(json.dumps(prof))
            # Package needs the ordinary fit mesh inventory, but no mesh content
            # is changed by the registration writer.
            for item in prof["equipment"]:
                item["file"] = "fitted_test_1.nif"
            (output / "armor-fitting.json").write_text(json.dumps(prof))
            from plugin import write_plugin

            write_plugin(
                output / "mod" / s.plugin_name,
                [
                    Record(
                        b"ARMA",
                        0x01000000 + i["addon_local_id"],
                        0,
                        [(b"RNAM", struct.pack("<I", 0x01000804))],
                    )
                    for i in prof["equipment"]
                ],
            )
            write_registration(output)
            self.assertEqual(validate_registration(output)["bindings"], 2)
            import zipfile

            with zipfile.ZipFile(package(output, s)) as archive:
                self.assertNotIn("VRM2SkyrimArmorPatch.esp", archive.namelist())
                for path in config_paths(s.plugin_name).values():
                    self.assertIn(path.as_posix(), archive.namelist())
            path = output / "mod" / config_paths(s.plugin_name)["armor"]
            path.write_text(path.read_text().replace("Independent.esp", "Other.esp"))
            with self.assertRaisesRegex(ValueError, "differs"):
                validate_registration(output)

    def test_legacy_equipment_edit_requests_require_reexport_before_work(self):
        from wizard import WizardApplication

        with tempfile.TemporaryDirectory() as temp:
            app = WizardApplication(temp)
            app.jobs["old"] = {
                "id": "old",
                "status": "complete",
                "armor_patch": "legacy.zip",
            }
            try:
                with self.assertRaisesRegex(ValueError, "SkyPatcher"):
                    app.start_edit("old", "mesh", b"invalid NIF", "missing Blender")
                self.assertFalse((Path(temp) / "edits").exists())
            finally:
                app.close()

    def test_runtime_checks_do_not_change_config_and_report_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            self.assertIn("missing_runtime", installation_status(data)["problems"])
            root = data / "SKSE/Plugins"
            root.mkdir(parents=True)
            (root / "SkyPatcher.dll").write_bytes(
                b"armorAddonsToAdd filterByArmorAddonsExcluded hasPlugins formsToAdd"
            )
            ini = root / "SkyPatcher.ini"
            ini.write_text(
                "[Patcher]\niEnableArmorPatching=1\niEnableFormlistPatching=1\n"
            )
            before = ini.read_bytes()
            self.assertTrue(installation_status(data)["ready"])
            self.assertIn(
                "missing_config", installation_status(data, "Missing.esp")["problems"]
            )
            self.assertEqual(ini.read_bytes(), before)
            ini.write_text(
                "[Patcher]\niEnableArmorPatching=0\niEnableFormlistPatching=banana\n"
            )
            self.assertIn("iEnableArmorPatching", installation_status(data)["problems"])
            self.assertIn(
                "iEnableFormlistPatching", installation_status(data)["problems"]
            )


class SkyPatcherGameTests(unittest.TestCase):
    def test_independent_exports_keep_dlc_footsteps_and_private_links(self):
        from environment import find_game

        game = find_game()
        if not game:
            self.skipTest("Local Skyrim.esm required")
        from build_npc import build_npc
        from game_catalog import GameCatalog
        from official_catalog import OfficialCatalog
        from plugin_validation import validate_private_records
        from skypatcher import footstep_bindings

        catalog = GameCatalog(game / "Data")
        official = OfficialCatalog(game / "Data")
        armor = official.require("DLC2ClothesSkaalBoots", b"ARMO")
        source = next(
            a for a in official.addon_records(armor, "female") if a.values(b"SNDD")
        )
        owner, local = official.identity(armor)
        with tempfile.TemporaryDirectory() as temp:
            config_sets = []
            for name in ("FirstFitted", "SecondFitted"):
                out = Path(temp) / name
                out.mkdir()
                settings = FollowerSettings(
                    mod_id=name,
                    armor_support=True,
                    sitting_enabled=False,
                    fit_armors=[official.key(armor)],
                    appearance_source_sha256="a" * 64,
                    appearance_parts={
                        "body": [1],
                        "underwear": [2],
                        "fixed": [3],
                        "garments": [
                            dict(
                                id="coat",
                                name="Coat",
                                nodes=[4],
                                slot=44,
                                armor_type="clothing",
                                armor_rating=0,
                                weight=1,
                                value=1,
                                equipped=True,
                            )
                        ],
                    },
                )
                settings.save(out / "settings.json")
                prof = {
                    "plugin": settings.plugin_name,
                    "wardrobe_policy": "native_slots",
                    "equipment": [
                        dict(
                            editor_id=armor.editor_id,
                            original_form_id=armor.form_id,
                            origin_plugin=owner,
                            origin_local_id=local,
                            addon_local_id=0x1000,
                            source_addon_key=official.key(source),
                            slots=[37],
                            priority=0,
                            file="fitted_test_1.nif",
                        )
                    ],
                }
                (out / "armor-fitting.json").write_text(json.dumps(prof))
                path = build_npc(game / "Data", out, settings, catalog)
                parsed = follower_records(path)
                validate_private_records(parsed, settings, out)
                extra, refs = footstep_bindings(game / "Data", prof)
                self.assertIn("Dragonborn.esm", extra)
                addon = next(
                    r
                    for r in parsed
                    if r.kind == b"ARMA" and r.form_id & 0xFFFFFF == 0x1000
                )
                self.assertEqual(
                    addon.values(b"SNDD"), [struct.pack("<I", refs[0x1000])]
                )
                header = next(records(path))
                masters = [v.rstrip(b"\0").decode() for v in header.values(b"MAST")]
                self.assertTrue(all(n.endswith(".esm") for n in masters))
                self.assertIn("Dragonborn.esm", masters)
                from gear_head_runtime import IDS

                for record in parsed:
                    if record.form_id in (
                        IDS["FaceHidingEquipment"],
                        IDS["HairHidingEquipment"],
                    ):
                        self.assertTrue(
                            all(
                                struct.unpack("<I", value)[0] >> 24 == 1
                                for value in record.values(b"LNAM")
                            )
                        )
                write_registration(out)
                validate_registration(out)
                import zipfile

                with zipfile.ZipFile(package(out, settings)) as archive:
                    self.assertIsNone(archive.testzip())
                    config_sets.append(set(archive.namelist()))
            self.assertFalse(config_sets[0] & config_sets[1])
