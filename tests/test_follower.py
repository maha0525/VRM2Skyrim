"""Semantic checks of the actual generated follower records against Skyrim.esm."""
from dataclasses import asdict
from pathlib import Path
import struct
import tempfile
import unittest

from build_npc import build_npc, NPC_ID, RACE_ID, REFERENCE_ID
from environment import find_game
from game_catalog import GameCatalog
from plugin import records
from settings import FollowerSettings

ROOT = Path(__file__).resolve().parents[1]


class SettingsTests(unittest.TestCase):
    def test_bad_configuration_is_rejected(self):
        for options in ({"mod_id": "../escape"}, {"mod_id": "unsafe/name"}, {"health": 0},
                        {"min_level": 30, "max_level": 5}, {"height_scale": float("nan")},
                        {"skills": {"OneHanded": 80}}, {"perks": None}, {"skills": []},
                        {"marriage": "true"}, {"perks": [{"editor_id": "x", "rank": -1}]}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                FollowerSettings(**options)
        with self.assertRaises(ValueError):
            FollowerSettings.from_dict({"silently_ignored_setting": 1})

    def test_unicode_name_roundtrip_and_safe_id(self):
        settings = FollowerSettings(npc_name="ソフィー", mod_name="ソフィーと冒険")
        self.assertTrue(settings.mod_id.startswith("Avatar_"))
        self.assertEqual(asdict(FollowerSettings.from_dict(asdict(settings))), asdict(settings))
        self.assertEqual(FollowerSettings(mod_name="123").mod_id, "Avatar_123")


@unittest.skipUnless(find_game(), "Local Skyrim.esm required for integration checks")
class FollowerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = find_game()
        cls.catalog = GameCatalog(cls.game / "Data")
        (ROOT / "build/test-tmp").mkdir(parents=True, exist_ok=True)

    def build(self, settings):
        temp = tempfile.TemporaryDirectory(dir=ROOT / "build/test-tmp")
        self.addCleanup(temp.cleanup)
        path = build_npc(self.game / "Data", Path(temp.name), settings, self.catalog)
        parsed = list(records(path))
        return parsed, {record.kind: record for record in parsed}

    def test_recruitment_relationship_and_temple_group(self):
        settings = FollowerSettings(npc_name="ソフィー", mod_name="TempleFollower")
        parsed, by_kind = self.build(settings)
        npc = by_kind[b"NPC_"]
        factions = {struct.unpack_from("<I", value)[0]: struct.unpack_from("<b", value, 4)[0]
                    for value in npc.values(b"SNAM")}
        self.assertEqual(factions[self.catalog.require("PotentialFollowerFaction").form_id], 0)
        self.assertEqual(factions[self.catalog.require("CurrentFollowerFaction").form_id], -1)
        self.assertEqual(struct.unpack("<IIHBBI", by_kind[b"RELA"].values(b"DATA")[0]), (NPC_ID, 7, 1, 0, 0, 0))
        actor = by_kind[b"ACHR"]
        cell = self.catalog.require("WhiterunTempleofKynareth")
        marker = self.catalog.require("WhiterunTempleofKynarethCenterMarker")
        self.assertEqual(actor.groups[-2:], ((struct.pack("<I", cell.form_id), 6), (struct.pack("<I", cell.form_id), 8)))
        self.assertEqual(actor.values(b"DATA"), marker.values(b"DATA"))
        self.assertEqual(actor.flags & 0x400, 0x400)
        self.assertEqual(by_kind[b"CELL"].fields, cell.fields)
        self.assertEqual(npc.values(b"FULL"), ["ソフィー\0".encode("utf8")])
        self.assertEqual(by_kind[b"RACE"].form_id, RACE_ID)
        self.assertEqual(actor.form_id, REFERENCE_ID)
        self.assertEqual(len({record.form_id for record in parsed if record.kind not in {b"TES4", b"CELL"}}), 7)
        groups = {record.groups[:index] for record in parsed for index in range(1, len(record.groups) + 1)}
        self.assertEqual(struct.unpack("<fII", by_kind[b"TES4"].values(b"HEDR")[0])[1], len(parsed) - 1 + len(groups))

    def test_all_custom_fields_reach_the_binary(self):
        settings = FollowerSettings(npc_name="Configured", mod_name="ConfiguredFollower", sex="male", voice="MaleNord",
                                    combat_class="CombatMageDestruction", combat_style="csHumanMagic",
                                    level_mode="fixed", level=27, auto_calculate=False, health=1, magicka=0, stamina=325,
                                    min_level=1, max_level=90, protection="essential", confidence=3, aggression=0, morality=2,
                                    marriage=True, height_scale=.8, weapon="HuntingBow", ammunition="IronArrow",
                                    perks=[{"editor_id": "Armsman00", "rank": 0}], spells=["Firebolt"],
                                    skills={"OneHanded": 75}, spawn_offset_x=64, spawn_offset_y=-32)
        _, by_kind = self.build(settings)
        npc = by_kind[b"NPC_"]
        flags, magicka, stamina, level = struct.unpack_from("<IhhH", npc.values(b"ACBS")[0])
        self.assertEqual(flags & (1 | 2 | 0x10 | 0x80 | 0x800), 2)
        self.assertEqual((magicka, stamina, level), (-50, 275, 27))
        self.assertEqual(struct.unpack_from("<h", npc.values(b"ACBS")[0], 20)[0], -49)
        self.assertEqual(struct.unpack_from("<HHH", npc.values(b"DNAM")[0], 36), (1, 0, 325))
        self.assertEqual(npc.values(b"DNAM")[0][0], 75)
        self.assertEqual(npc.values(b"AIDT")[0][:6], bytes((0, 3, 50, 2, 0, 2)))
        for field, name in ((b"VTCK", settings.voice), (b"CNAM", settings.combat_class), (b"ZNAM", settings.combat_style)):
            self.assertEqual(npc.values(field), [struct.pack("<I", self.catalog.require(name).form_id)])
        self.assertEqual(struct.unpack("<I", npc.values(b"PRKZ")[0])[0], 1)
        self.assertEqual(npc.values(b"PRKR"), [struct.pack("<IB3x", self.catalog.require("Armsman00").form_id, 0)])
        self.assertEqual(npc.values(b"SPLO"), [struct.pack("<I", self.catalog.require("Firebolt").form_id)])
        self.assertEqual(len(npc.values(b"CNTO")), 2)
        marker = struct.unpack("<6f", self.catalog.require("WhiterunTempleofKynarethCenterMarker").values(b"DATA")[0])
        position = struct.unpack("<6f", by_kind[b"ACHR"].values(b"DATA")[0])
        self.assertAlmostEqual(position[0] - marker[0], 64, places=4)
        self.assertAlmostEqual(position[1] - marker[1], -32, places=4)

    def test_two_mods_use_disjoint_names_and_paths(self):
        configs = [FollowerSettings(mod_name="AlphaFollower"), FollowerSettings(mod_name="BetaFollower")]
        parsed = [self.build(config)[0] for config in configs]
        names = [{record.editor_id for record in items if record.kind not in {b"CELL", b"TES4"}} for items in parsed]
        self.assertFalse(names[0] & names[1])
        paths = [{data for record in items for tag, data in record.fields if tag in {b"ANAM", b"MOD2", b"MOD3"}}
                 for items in parsed]
        self.assertFalse(paths[0] & paths[1])
        self.assertNotEqual(configs[0].plugin_name, configs[1].plugin_name)

    def test_unsupported_voice_and_perk_rank_are_rejected(self):
        unsupported = next(record for record in self.catalog.choices(b"VTYP") if record.form_id not in self.catalog.follower_voice_ids)
        with self.assertRaises(ValueError):
            self.catalog.validate_settings(FollowerSettings(voice=unsupported.editor_id))
        with self.assertRaises(ValueError):
            self.catalog.validate_settings(FollowerSettings(perks=[{"editor_id": "Armsman00", "rank": 255}]))


if __name__ == "__main__":
    unittest.main()
