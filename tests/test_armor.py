"""Geometry invariants and a combined patch against a user's installed master."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from armor_geometry import BodyField, canonical_bone
from armor_catalog import native_partition, partition_slot
from armor_patch import build_patch
from environment import find_game
from game_catalog import GameCatalog
from plugin import Record, records, write_plugin
from settings import FollowerSettings


class ArmorFieldTests(unittest.TestCase):
    def test_hood_and_helmet_native_partitions_are_not_plain_hair(self):
        for native, slot in ((130, 30), (131, 31), (141, 41), (142, 42), (143, 43)):
            self.assertEqual(native_partition(native, slot), native)
            self.assertEqual(partition_slot(native, slot), slot)
        self.assertEqual(native_partition(0, 31), 31)
        # A hood can contain ordinary hair and hood partitions at the same
        # equip layer; both native values must survive splitting.
        self.assertEqual({native_partition(p, 31) for p in (31, 131)}, {31, 131})
        self.assertEqual({partition_slot(p, 31) for p in (31, 131)}, {31})
    def test_reference_mapping_changes_equipment_not_target_skin(self):
        points = np.array([(x, y, z) for x in (-2., 0., 2.) for y in (-1., 1.) for z in (1., 3., 4.)])
        target = points * (.6, .8, 1.5)
        target.setflags(write=False)
        source_joints = {"NPC Pelvis [Pelv]": np.zeros(3), "NPC Spine [Spn0]": np.array((0., 0., 5.))}
        target_joints = {n: p * (1., 1., 1.5) for n, p in source_joints.items()}
        weights = {"NPC Pelvis [Pelv]": [(i, 1.) for i in range(len(points))]}
        before = points.copy(), target.copy()
        field = BodyField(points, weights, target, weights, source_joints, target_joints)
        np.testing.assert_allclose(field.deform(points, weights), target, atol=1e-8)
        np.testing.assert_array_equal(points, before[0])
        np.testing.assert_array_equal(target, before[1])
        # Auxiliary contributions can repeat a vertex under the same canonical
        # bone; they must be summed rather than lost through indexed assignment.
        repeated = {"NPC Pelvis [Pelv]": [(i, .4) for i in range(len(points))] + [(i, .6) for i in range(len(points))]}
        np.testing.assert_allclose(field.coarse(points, repeated), target, atol=1e-8)

    def test_unmapped_and_invalid_equipment_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_bone("Accessory", {"Accessory": "Accessory"})
        for value in (["../escape"], ["ArmorIronBoots", "ArmorIronBoots"], "ArmorIronBoots", [None]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FollowerSettings(fit_armors=value)


class ArmorPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        game = find_game()
        if not game:
            raise unittest.SkipTest("Requires a local Skyrim.esm")
        cls.data = Path(game) / "Data"
        cls.catalog = GameCatalog(cls.data)

    def test_native_patch_does_not_reactivate_retired_switch_lists(self):
        original = self.catalog.require('ArmorIronBoots', b'ARMO')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = []
            for index, policy in enumerate(('legacy', 'native_slots')):
                name = 'PolicyFollower'+str(index)
                path = root/name
                path.mkdir()
                addon = Record(b'ARMA', 0x01000880, 0, [(b'EDID', (name+'AA\0').encode()),
                                                       (b'RNAM', struct.pack('<I', 0x01000804))])
                retired = Record(b'FLST', 0x01000846, 0, [(b'EDID', (name+'FeetEquipment\0').encode())])
                write_plugin(path/'mod'/(name+'.esp'), [addon, retired])
                manifest = path/'armor-fitting.json'
                manifest.write_text(json.dumps({'plugin': name+'.esp', 'wardrobe_policy': policy,
                                                'equipment': [{'editor_id': original.editor_id,
                                                               'original_form_id': original.form_id,
                                                               'addon_local_id': 0x880, 'armor_mask': 128}]}))
                manifests.append(manifest)
            build_patch(self.data, manifests, root/'patch')
            loaded = list(records(root/'patch/mod/VRM2SkyrimArmorPatch.esp'))
            lists = [r for r in loaded if r.kind == b'FLST']
            self.assertEqual([(r.form_id, r.values(b'LNAM')) for r in lists],
                             [(0x01000846, [struct.pack('<I', original.form_id)])])
            armor = next(r for r in loaded if r.kind == b'ARMO')
            self.assertEqual(armor.values(b'BOD2'), original.values(b'BOD2'))

    def test_two_followers_keep_both_addons_and_original_armor_stats(self):
        original = self.catalog.require("ArmorIronBoots", b"ARMO")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = []
            for name in ("FirstFittedFollower", "SecondFittedFollower"):
                path = root / name
                path.mkdir()
                addon = Record(b"ARMA", 0x01000880, 0, [(b"EDID", (name + "AA\0").encode()),
                                                       (b"RNAM", struct.pack("<I", 0x01000804))])
                write_plugin(path / "mod" / (name + ".esp"), [addon])
                manifest = path / "armor-fitting.json"
                manifest.write_text(json.dumps({"plugin": name + ".esp", "equipment": [
                    {"editor_id": original.editor_id, "original_form_id": original.form_id, "addon_local_id": 0x880}]}))
                manifests.append(manifest)
            build_patch(self.data, manifests, root / "patch")
            loaded = list(records(root / "patch/mod/VRM2SkyrimArmorPatch.esp"))
            header, armor = loaded
            self.assertEqual(header.values(b"MAST"), [b"Skyrim.esm\0", b"FirstFittedFollower.esp\0", b"SecondFittedFollower.esp\0"])
            self.assertEqual(armor.values(b"MODL"), original.values(b"MODL") + [struct.pack("<I", 0x01000880), struct.pack("<I", 0x02000880)])
            for tag in (b"DATA", b"DNAM", b"BOD2", b"KWDA", b"EITM"):
                self.assertEqual(armor.values(tag), original.values(tag))
            self.assertEqual(armor.values(b"FULL"), [(self.catalog.label(original) + "\0").encode("utf8")])
            with self.assertRaises(ValueError):
                build_patch(self.data, [manifests[0], manifests[0]], root / "duplicate")


if __name__ == "__main__":
    unittest.main()
