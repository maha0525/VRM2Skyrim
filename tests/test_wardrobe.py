"""Wardrobe source coverage and real Skyrim record linkage, independent of UI."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest

from build_npc import appearance_records, build_npc, ARMOR_ID
from head_visibility import EMPTY_HEAD_ID, configure_native_head, head_records, validate_head_visibility
from environment import find_game
from game_catalog import GameCatalog
from plugin import Record, records
from settings import FollowerSettings
from wardrobe import suggest_role, validate_source, item_kind, keyword_names, GARMENT_SLOTS
from parallel_rigs import follower_links, propagate_pose
import numpy as np


def wardrobe_settings(**overrides):
    garment = {"id": "coat", "name": "Coat", "nodes": [4], "slot": 44, "armor_type": "clothing",
               "armor_rating": 0, "weight": .5, "value": 7, "equipped": True}
    parts = {"body": [1], "underwear": [2], "fixed": [3], "garments": [garment]}
    values = {"armor_support": True, "appearance_source_sha256": "a" * 64, "appearance_parts": parts}
    values.update(overrides)
    return FollowerSettings(**values)


class WardrobeTests(unittest.TestCase):
    def test_usage_keywords_do_not_change_equipment_replacement_or_slots(self):
        garment = wardrobe_settings().appearance_parts['garments'][0]
        self.assertEqual(item_kind(garment), 'body')
        self.assertEqual(GARMENT_SLOTS[:5], (53, 54, 55, 56, 57))
        tights = {**garment, 'name': 'tights', 'slot': 47, 'equipment_group': 'accessory'}
        self.assertEqual(item_kind(tights), 'legs')
        self.assertEqual(keyword_names(tights), ['ArmorClothing', 'VendorItemClothing', 'ClothingBody'])
        self.assertEqual(keyword_names({**tights, 'item_kind': 'feet', 'armor_type': 'heavy'}),
                         ['ArmorHeavy', 'VendorItemArmor', 'ArmorBoots'])
        parts = copy.deepcopy(wardrobe_settings().appearance_parts)
        parts['garments'][0]['item_kind'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'item kind'):
            wardrobe_settings(appearance_parts=parts)

    def test_native_head_has_no_worn_item_dependency(self):
        class Catalog:
            def require(self, name, kind):
                fields = [(b"ETYP", struct.pack("<I", 0x13F42))] if kind == b"ARMO" else []
                return Record(kind, 0x1234, 0, fields)

        for fitting in (False, True):
            settings = wardrobe_settings(fit_armors=["ArmorIronBoots"] if fitting else [])
            generated, _ = appearance_records(settings, Catalog())
            npc = Record(b'NPC_', 0x01000800, 0, [(b'EDID', (settings.prefix+'NPC\0').encode()),
                                                (b'PNAM', struct.pack('<I', 0x51176))])
            race = Record(b'RACE', 0x01000804, 0, [(b'EDID', (settings.prefix+'Race\0').encode()),
                                                (b'DATA', bytes(64)), (b'NAM0', b'')])
            configure_native_head(npc, race)
            generated += [npc, race, *head_records(settings, race.form_id)]
            report = validate_head_visibility(generated, settings)
            self.assertFalse(report['depends_on_equipped_head_cover'])
            outfit = next(r for r in generated if r.kind == b"OTFT")
            # AFT can empty/replace the outfit without restoring human geometry.
            outfit.replace(b"INAM", b"")
            self.assertEqual(validate_head_visibility(generated, settings)['native_head_geometry'], 'empty')
            npc.replace(b'PNAM', struct.pack('<I', 0x51176))
            with self.assertRaisesRegex(ValueError, 'NPC still uses native human'):
                validate_head_visibility(generated, settings)
            npc.replace(b'PNAM', struct.pack('<I', EMPTY_HEAD_ID))
            race.replace(b'HEAD', struct.pack('<I', 0x51176))
            with self.assertRaisesRegex(ValueError, 'Race still supplies native human'):
                validate_head_visibility(generated, settings)

    def test_secondary_rigs_need_names_geometry_and_unique_matches(self):
        primary = {"hips": "Hips", "spine": "Spine", "head": "Head", "leftFoot": "Foot"}
        positions = {"Hips": np.array([0., 0, 1]), "Spine": np.array([0., 0, 1.3]),
                     "Head": np.array([0., 0, 1.7]), "Foot": np.array([0., 0, 0])}
        positions.update({name + "_2": point + [.01, 0, 0] for name, point in list(positions.items())})
        owners = {name: "secondary" if name.endswith("_2") else "body" for name in positions}
        labels = {name: name for name in positions}
        links, report = follower_links(positions, labels, owners, primary)
        self.assertEqual(len(links), 4)
        self.assertEqual(len(report), 1)
        transforms = {name: np.eye(4) for name in positions}
        transforms["Head"][:3, 3] = [1, 2, 3]
        parents = {name: None for name in positions}
        propagate_pose(transforms, parents, owners, links)
        np.testing.assert_array_equal(transforms["Head_2"], transforms["Head"])
        far = {name: point + [10, 0, 0] if name.endswith("_2") else point for name, point in positions.items()}
        self.assertFalse(follower_links(far, labels, owners, primary)[0])
        positions["Head_3"] = positions["Head_2"].copy()
        labels["Head_3"], owners["Head_3"] = "Head_3", "secondary"
        with self.assertRaises(ValueError):
            follower_links(positions, labels, owners, primary)

    def test_duplicate_classification_and_reserved_slot_rejected(self):
        settings = wardrobe_settings()
        for change in ("duplicate", "slot", "rating", "id", "empty", "collision"):
            parts = copy.deepcopy(settings.appearance_parts)
            garment = parts["garments"][0]
            if change == "duplicate":
                parts["body"].append(2)
            elif change == "slot":
                garment["slot"] = 32
            elif change == "rating":
                garment["armor_rating"] = float("nan")
            elif change == "id":
                garment["id"] = "../escape"
            elif change == "empty":
                parts["body"] = []
            else:
                parts["garments"].append({**garment, "id": "other", "nodes": [5]})
            with self.subTest(change=change), self.assertRaises(ValueError):
                wardrobe_settings(appearance_parts=parts)

    def test_source_digest_and_exact_mesh_coverage(self):
        settings = wardrobe_settings()
        report = {"sha256": "a" * 64, "parts": [{"node": n} for n in range(1, 5)]}
        validate_source(settings, report)
        for invalid in ({**report, "sha256": "b" * 64}, {**report, "parts": report["parts"] + [{"node": 5}]}):
            with self.assertRaises(ValueError):
                validate_source(settings, invalid)
        # Keeping a saved classification while switching to fixed appearance is safe.
        validate_source(wardrobe_settings(armor_support=False), invalid)

    def test_face_materials_do_not_turn_a_face_named_body_into_torso(self):
        self.assertEqual(suggest_role("Body", ["Face", "Face_Eye", "AlphaParts_Unlit"]), "fixed")
        self.assertEqual(suggest_role("Body2", ["Body", "Body_Stencil"]), "body")
        self.assertEqual(suggest_role("Underwear_Bra", ["Underwear"]), "underwear")


@unittest.skipUnless(find_game(), "Local Skyrim.esm required")
class WardrobeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = find_game()
        cls.catalog = GameCatalog(cls.game / "Data")

    def test_skin_and_initial_clothing_are_separate_records(self):
        settings = wardrobe_settings()
        extra = {**settings.appearance_parts["garments"][0], "id": "boots", "name": "Boots", "nodes": [5],
                 "slot": 45, "armor_type": "heavy", "armor_rating": 12.5, "equipped": False}
        settings.appearance_parts["garments"].append(extra)
        with tempfile.TemporaryDirectory() as temp:
            parsed = list(records(build_npc(self.game / "Data", Path(temp), settings, self.catalog)))
        by_id = {r.form_id: r for r in parsed}
        by_name = {r.editor_id: r for r in parsed}
        skin = by_id[ARMOR_ID]
        self.assertEqual(len(skin.values(b"MODL")), 3)
        self.assertEqual({struct.unpack_from("<I", by_id[struct.unpack("<I", ref)[0]].values(b"BOD2")[0])[0]
                          for ref in skin.values(b"MODL")}, {1 << 2, 1 << 22, 1 << 30})
        coat = by_name[settings.prefix + "Garment_coat"]
        boots = by_name[settings.prefix + "Garment_boots"]
        self.assertEqual(coat.flags & 4, 0)
        self.assertEqual(coat.values(b"ETYP"), self.catalog.require("ClothesFarmClothes01").values(b"ETYP"))
        self.assertTrue(coat.values(b"MOD2"))
        for item, names in ((coat, ['ArmorClothing', 'VendorItemClothing', 'ClothingBody']),
                            (boots, ['ArmorHeavy', 'VendorItemArmor', 'ArmorBoots'])):
            self.assertEqual(item.values(b'KSIZ'), [struct.pack('<I', len(names))])
            self.assertEqual(item.values(b'KWDA'), [b''.join(struct.pack('<I', self.catalog.require(n,b'KYWD').form_id) for n in names)])
        self.assertEqual(by_name[settings.prefix + "Outfit"].values(b"INAM"), [b''])
        self.assertIn(struct.pack('<Ii', coat.form_id, 1), by_name[settings.prefix+'NPC'].values(b'CNTO'))
        validate_head_visibility(parsed, settings)
        self.assertEqual(struct.unpack("<i", boots.values(b"DNAM")[0])[0], 1250)
        self.assertIn(struct.pack("<Ii", boots.form_id, 1), by_name[settings.prefix + "NPC"].values(b"CNTO"))
        self.assertEqual(len({r.form_id for r in parsed}), len(parsed))
        self.assertTrue(all(r.values(b"RNAM") == [struct.pack("<I", by_name[settings.prefix + "Race"].form_id)]
                            for r in parsed if r.kind == b"ARMA"))


if __name__ == "__main__":
    unittest.main()
