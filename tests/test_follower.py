"""Semantic checks of the actual generated follower records against Skyrim.esm."""
from dataclasses import asdict
from pathlib import Path
import struct
import tempfile
import unittest

from build_npc import build_npc, NPC_ID, RACE_ID, REFERENCE_ID, ADDON_ID, ARMOR_ID, SLOT_MASK
from environment import find_game
from game_catalog import GameCatalog, class_growth
from plugin import records, Record
from settings import FollowerSettings

ROOT = Path(__file__).resolve().parents[1]


class SettingsTests(unittest.TestCase):
    def test_physics_selection_roundtrip_without_wardrobe(self):
        values = dict(armor_support=False, physics_enabled=True,
                      physics_nodes=[756, 761, 932], physics_source_sha256='a'*64)
        (ROOT/'build/test-tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/test-tmp') as directory:
            path = Path(directory)/'settings.json'
            FollowerSettings.from_dict(values).save(path)
            restored = FollowerSettings.load(path)
            for key, value in values.items():
                self.assertEqual(getattr(restored, key), value)
        legacy = FollowerSettings.from_dict({'physics_nodes': [756],
                                            'appearance_source_sha256': 'b'*64})
        self.assertEqual(legacy.physics_nodes, [756])
        self.assertEqual(legacy.physics_source_sha256, '')
        for invalid in (None, [], 1, 'not-a-hash', 'A'*64):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FollowerSettings(physics_source_sha256=invalid)

    def test_preset_roundtrip_preserves_customized_values_and_legacy_is_custom(self):
        self.assertEqual(FollowerSettings().combat_preset, 'warrior')
        values = dict(combat_preset='mage', combat_class='CombatWarrior1H',
                      combat_style='csHumanMissile', health=321, magicka=123,
                      weapon='HuntingBow', spells=['FastHealing'])
        (ROOT/'build/test-tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/test-tmp') as directory:
            path = Path(directory)/'settings.json'
            FollowerSettings(**values).save(path)
            restored = FollowerSettings.load(path)
            for key, value in values.items():
                self.assertEqual(getattr(restored, key), value)
        legacy = {k: v for k, v in values.items() if k != 'combat_preset'}
        self.assertEqual(FollowerSettings.from_dict(legacy).combat_preset, 'custom')
        self.assertNotIn('combat_preset', legacy)
        for invalid in ('unknown', None, [], True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FollowerSettings(combat_preset=invalid)

    def test_new_defaults_and_explicit_imported_protection(self):
        self.assertEqual((FollowerSettings().protection, FollowerSettings().morality), ('essential', 0))
        old = FollowerSettings.from_dict({'protection': 'protected', 'morality': 3})
        self.assertEqual((old.protection, old.morality), ('protected', 3))

    def test_class_data_layout_and_short_data(self):
        data = bytes(6) + bytes(range(18)) + bytes(8) + bytes((4, 0, 2, 99))
        record = Record(b'CLAS', 1, 0, [(b'DATA', data)])
        growth = class_growth(record)
        self.assertEqual(growth['skills']['OneHanded'], 0)
        self.assertEqual(growth['skills']['Enchanting'], 17)
        self.assertEqual(growth['attributes'], {'health': 4, 'magicka': 0, 'stamina': 2})
        record.replace(b'DATA', bytes(35))
        self.assertIsNone(class_growth(record))

    def test_race_traits_inheritance_and_cycles(self):
        race = Record(b'RACE', 1, 0, [])
        base = Record(b'NPC_', 2, 0, [(b'RNAM', struct.pack('<I', 1))])
        data = bytearray(24)
        struct.pack_into('<H', data, 18, 1)
        child = Record(b'NPC_', 3, 0, [(b'ACBS', bytes(data)), (b'TPLT', struct.pack('<I', 2))])
        catalog = GameCatalog.__new__(GameCatalog)
        catalog.by_form_id = {1: race, 2: base, 3: child}
        self.assertIs(catalog.actor_race(child), race)
        base.fields = [(b'ACBS', bytes(data)), (b'TPLT', struct.pack('<I', 3))]
        self.assertIsNone(catalog.actor_race(child))

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

    def test_fixed_avatar_attaches_once_without_losing_equipment_exclusion(self):
        for physics in (False, True):
            with self.subTest(physics=physics):
                settings = FollowerSettings(physics_enabled=physics, physics_nodes=[1] if physics else [])
                parsed, by_kind = self.build(settings)
                addon = next(r for r in parsed if r.form_id == ADDON_ID)
                armor = next(r for r in parsed if r.form_id == ARMOR_ID)
                # One render attachment, matching convert_blender's fixed NIF
                # partition; ten exclusion slots must never become ten rigs.
                self.assertEqual(addon.kind, b'ARMA')
                self.assertEqual(struct.unpack('<II', addon.values(b'BOD2')[0]), (4, 2))
                self.assertEqual(struct.unpack('<II', armor.values(b'BOD2')[0]), (SLOT_MASK, 2))
                self.assertEqual(armor.values(b'MODL'), [struct.pack('<I', ADDON_ID)])
                self.assertEqual(by_kind[b'OTFT'].values(b'INAM'), [struct.pack('<I', ARMOR_ID)])
                self.assertEqual(by_kind[b'RACE'].values(b'WNAM'), [struct.pack('<I', ARMOR_ID)])
                for tag in (b'MOD2', b'MOD3'):
                    self.assertEqual(addon.values(tag), [(settings.asset_dir.replace('/', '\\')+'\\avatar.nif\0').encode()])

    def test_preset_label_does_not_change_generated_game_records(self):
        first, _ = self.build(FollowerSettings(combat_preset='mage'))
        second, _ = self.build(FollowerSettings(combat_preset='custom'))
        self.assertEqual([r.encode() for r in first], [r.encode() for r in second])

    def test_wizard_spells_are_castable_and_blade_is_the_faction_class(self):
        choices = self.catalog.json_choices('female')
        spells = {s['id'] for s in choices['spells']}
        self.assertIn('Firebolt', spells)
        self.assertIn('FastHealing', spells)
        self.assertNotIn('AbWolfIce', spells)
        self.assertNotIn('AltarAkatoshSpell', spells)
        blade = next(c for c in choices['classes'] if c['id'] == 'Blade')
        self.assertIn('ブレイズ', blade['label'])

    def test_class_weights_and_combat_style_usage_from_game(self):
        choices = self.catalog.json_choices()
        classes = {c['id']: c['growth'] for c in choices['classes']}
        self.assertEqual(classes['CombatWarrior1H']['skills']['OneHanded'], 3)
        self.assertEqual(classes['CombatWarrior1H']['attributes'], {'health': 4, 'magicka': 0, 'stamina': 2})
        self.assertEqual(classes['CombatMageDestruction']['skills']['Destruction'], 3)
        styles = {s['id']: s for s in choices['styles']}
        for key in ('csHumanMeleeLvl1', 'csHumanBoss2H', 'csHumanMissile', 'csHumanMagic'):
            self.assertTrue(styles[key]['humanoid'], key)
        self.assertFalse(styles['csMammoth']['humanoid'])
        self.assertTrue(styles['csMammoth']['used_by'])

    def test_skill_tree_categories_separate_stages_from_effect_ranks(self):
        choices = self.catalog.json_choices()
        perks = {p['id']: p for p in choices['perks']}
        spells = {s['id']: s for s in choices['spells']}
        for index, key in enumerate(('Stealth00', 'Stealth20', 'Stealth40', 'Stealth60', 'Stealth80')):
            self.assertEqual(perks[key]['categories'], ['Sneak'])
            self.assertEqual(perks[key]['stage'], {'index': index+1, 'total': 5})
            self.assertEqual(perks[key]['effect_ranks'], [0])
        self.assertEqual(perks['QuietCasting']['categories'], ['Illusion'])
        for key, school in [('Firebolt', 'Destruction'), ('Healing', 'Restoration'),
                            ('Muffle', 'Illusion'), ('Oakflesh', 'Alteration'),
                            ('ConjureFlameAtronach', 'Conjuration')]:
            self.assertEqual(spells[key]['categories'], [school])
        self.assertTrue(all(c['growth'] is not None for c in choices['classes']))
        with self.assertRaisesRegex(ValueError, '効果がありません'):
            self.catalog.validate_settings(FollowerSettings(perks=[{'editor_id': 'Stealth00', 'rank': 1}]))

    def test_default_flags_and_all_manual_skills_reach_plugin(self):
        from settings import SKILLS
        values = {key: 40 + index for index, key in enumerate(SKILLS)}
        _, by_kind = self.build(FollowerSettings(auto_calculate=False, skills=values))
        npc = by_kind[b'NPC_']
        flags = struct.unpack_from('<I', npc.values(b'ACBS')[0])[0]
        self.assertEqual(flags & (2 | 0x800 | 0x10), 2)
        self.assertEqual(npc.values(b'AIDT')[0][3], 0)
        self.assertEqual(npc.values(b'DNAM')[0][:18], bytes(values.values()))

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
        self.assertEqual(len({record.form_id for record in parsed if record.kind not in {b"TES4", b"CELL"}}), 9)
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
