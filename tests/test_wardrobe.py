"""Wardrobe source coverage and real Skyrim record linkage, independent of UI."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest

from build_npc import build_npc, ARMOR_ID
from environment import find_game
from game_catalog import GameCatalog
from plugin import records
from settings import FollowerSettings
from wardrobe import suggest_role, validate_source
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
        self.assertEqual(struct.unpack("<I", by_name[settings.prefix + "Outfit"].values(b"INAM")[0])[0], coat.form_id)
        self.assertEqual(struct.unpack("<i", boots.values(b"DNAM")[0])[0], 1250)
        self.assertIn(struct.pack("<Ii", boots.form_id, 1), by_name[settings.prefix + "NPC"].values(b"CNTO"))
        self.assertEqual(len({r.form_id for r in parsed}), len(parsed))
        self.assertTrue(all(r.values(b"RNAM") == [struct.pack("<I", by_name[settings.prefix + "Race"].form_id)]
                            for r in parsed if r.kind == b"ARMA"))


if __name__ == "__main__":
    unittest.main()
