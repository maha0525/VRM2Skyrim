import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import numpy as np

from inspect_vrm import humanoid_map, read_glb
from plugin import Record, parse_fields, records, subrecord, write_plugin
from preserved_pose import align_rotation, palm_basis


class FormatTests(unittest.TestCase):
    def test_pose_rotation_preserves_lengths_and_handedness(self):
        for target in ((0, 0, 1), (-1, 0, 0), (.3, -.7, .6)):
            rotation = align_rotation((1, 0, 0), target)
            np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-10)
            self.assertAlmostEqual(np.linalg.det(rotation), 1)
            np.testing.assert_allclose(rotation @ (1, 0, 0),
                                       np.array(target) / np.linalg.norm(target), atol=1e-10)

    def test_palm_twist_is_not_lost_when_along_axis_matches(self):
        names = {"left" + key: key for key in ("Hand", "MiddleProximal", "IndexProximal", "LittleProximal")}
        source = {"Hand": np.array((0., 0., 0.)), "MiddleProximal": np.array((1., 0., 0.)),
                  "IndexProximal": np.array((1., -1., 0.)), "LittleProximal": np.array((1., 1., 0.))}
        quarter_turn = np.array(((1., 0., 0.), (0., 0., -1.), (0., 1., 0.)))
        target = {key: quarter_turn @ value for key, value in source.items()}
        rotation = palm_basis(target, names, "left") @ palm_basis(source, names, "left").T
        np.testing.assert_allclose(rotation, quarter_turn, atol=1e-10)

    def test_extended_field_and_truncation(self):
        payload = b"test" * 20000
        self.assertEqual(parse_fields(subrecord(b"DATA", payload)), [(b"DATA", payload)])
        with self.assertRaises(ValueError):
            parse_fields(subrecord(b"DATA", payload)[:-1])

    def test_compressed_record(self):
        payload = subrecord(b"EDID", b"TestNPC\0")
        compressed = struct.pack("<I", len(payload)) + zlib.compress(payload)
        header = struct.pack("<4sIIIIHH", b"NPC_", len(compressed), 0x40000, 0x01000800, 0, 44, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.esp"
            path.write_bytes(header + compressed)
            record = list(records(path))[0]
            self.assertEqual(record.editor_id, "TestNPC")
            self.assertEqual(record.form_id, 0x01000800)

    def test_plugin_header_counts_groups_and_local_references(self):
        items = [Record(b"NPC_", 0x01000800, 0, [(b"EDID", b"NPC\0"), (b"DOFT", struct.pack("<I", 0x01000801))]),
                 Record(b"OTFT", 0x01000801, 0, [(b"EDID", b"Outfit\0")])]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.esp"
            write_plugin(path, items)
            parsed = list(records(path))
            _, count, next_id = struct.unpack("<fII", parsed[0].values(b"HEDR")[0])
            self.assertEqual(count, 4)  # two records plus two groups, excluding TES4
            self.assertGreater(next_id, 0x801)
            self.assertEqual(parsed[0].values(b"MAST"), [b"Skyrim.esm\0"])
            self.assertEqual(parsed[0].flags & 0x80, 0)  # strings are not localized IDs
            self.assertEqual({r.form_id for r in parsed[1:]}, {item.form_id for item in items})

    def test_vrm_version_metadata(self):
        vrm0 = {"extensions": {"VRM": {"humanoid": {"humanBones": [{"bone": "hips", "node": 2}]}}}}
        vrm1 = {"extensions": {"VRMC_vrm": {"humanoid": {"humanBones": {"hips": {"node": 2}}}}}}
        self.assertEqual(humanoid_map(vrm0), {"hips": 2})
        self.assertEqual(humanoid_map(vrm1), {"hips": 2})

    def test_vrm_zero_thumb_semantics_match_vrm_one(self):
        old = {"extensions": {"VRM": {"humanoid": {"humanBones": [
            {"bone": "leftThumbProximal", "node": 3}, {"bone": "leftThumbIntermediate", "node": 4},
            {"bone": "leftThumbDistal", "node": 5}]}}}}
        self.assertEqual(humanoid_map(old), {"leftThumbMetacarpal": 3, "leftThumbProximal": 4, "leftThumbDistal": 5})

    def test_glb_length_contract(self):
        payload = json.dumps({"asset": {"version": "2.0"}}).encode()
        payload += b" " * (-len(payload) % 4)
        blob = struct.pack("<4sII", b"glTF", 2, 20 + len(payload))
        blob += struct.pack("<II", len(payload), 0x4E4F534A) + payload
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.vrm"
            path.write_bytes(blob)
            document, _ = read_glb(path)
            self.assertEqual(document["asset"]["version"], "2.0")
            path.write_bytes(blob[:-1])
            with self.assertRaises(ValueError):
                read_glb(path)

    def test_extract_vrm_expressions_vrm1_and_vrm0_and_empty(self):
        from expressions import extract_vrm_expressions
        vrm1 = {
            "nodes": [{"name": "Head", "mesh": 0}],
            "meshes": [{"primitives": [{"targets": [{"POSITION": 0}, {"POSITION": 1}]}]}],
            "extensions": {"VRMC_vrm": {"expressions": {
                "preset": {"aa": {"morphTargetBinds": [{"node": 0, "index": 0, "weight": 1.0}]}},
                "custom": {"brow_angry": {"morphTargetBinds": [{"node": 0, "index": 1, "weight": 0.8}]}},
            }}},
        }
        parsed1 = extract_vrm_expressions(vrm1)
        self.assertEqual(parsed1["vrm_version"], "1.0")
        self.assertEqual(parsed1["nodes"], [0])
        self.assertEqual(parsed1["expressions"]["aa"], [(0, 0, 1.0)])
        self.assertEqual(parsed1["expressions"]["brow_angry"], [(0, 1, 0.8)])

        vrm0 = {
            "nodes": [{"name": "Head", "mesh": 0}],
            "meshes": [{"primitives": [{"targets": [{"POSITION": 0}]}]}],
            "extensions": {"VRM": {"blendShapeMaster": {"blendShapeGroups": [
                {"name": "Joy", "presetName": "joy", "binds": [{"mesh": 0, "index": 0, "weight": 100}]}
            ]}}},
        }
        parsed0 = extract_vrm_expressions(vrm0)
        self.assertEqual(parsed0["vrm_version"], "0.x")
        self.assertEqual(parsed0["expressions"]["happy"], [(0, 0, 1.0)])

        empty = {"nodes": [{"name": "Body", "mesh": 0}], "meshes": [{"primitives": [{}]}]}
        self.assertEqual(extract_vrm_expressions(empty)["nodes"], [])

    def test_synthesize_skyrim_morph_deltas_lr_split(self):
        from expressions import SKYRIM_EXPRESSION_MORPHS, synthesize_skyrim_morph_deltas
        # Skyrim actor space: -X = actor left, +X = actor right.
        basis = np.array([[-2.0, 0.0, 100.0], [2.0, 0.0, 100.0]])
        deltas = {0: np.array([[0.0, 0.0, -1.0], [0.0, 0.0, -1.0]])}
        exprs = {"blink": [(0, 0, 1.0)], "aa": [(0, 0, 1.0)]}
        out = synthesize_skyrim_morph_deltas(basis, deltas, exprs, 0)
        self.assertEqual(tuple(out.keys()), SKYRIM_EXPRESSION_MORPHS)
        self.assertAlmostEqual(out["BlinkLeft"][0, 2], -1.0, places=5)
        self.assertAlmostEqual(out["BlinkLeft"][1, 2], 0.0, places=5)
        self.assertAlmostEqual(out["BlinkRight"][0, 2], 0.0, places=5)
        self.assertAlmostEqual(out["BlinkRight"][1, 2], -1.0, places=5)
        self.assertAlmostEqual(out["BigAah"][0, 2], -1.0, places=5)
        self.assertAlmostEqual(out["Aah"][0, 2], -0.85, places=5)

    def test_facial_head_records_and_remap(self):
        from expressions import EXTRA_HDPT_BASE_ID
        from follower_plugin import remap
        from head_visibility import EMPTY_HEAD_ID, head_records
        from settings import FollowerSettings
        settings = FollowerSettings(npc_name="Test", mod_name="TestFollower")
        facial = {"enabled": True, "parts": [
            {"edid": settings.prefix + "FacePart_0", "nif": f"meshes/{settings.asset_dir}/face_part_0.nif",
             "tri": f"meshes/{settings.asset_dir}/face_part_0.tri"},
            {"edid": settings.prefix + "FacePart_1", "nif": f"meshes/{settings.asset_dir}/face_part_1.nif",
             "tri": f"meshes/{settings.asset_dir}/face_part_1.tri"},
        ]}
        recs = head_records(settings, 0x01000804, facial=facial)
        by_id = {r.form_id: r for r in recs}
        primary = by_id[EMPTY_HEAD_ID]
        extra = by_id[EXTRA_HDPT_BASE_ID]
        self.assertEqual(primary.values(b"NAM0"), [struct.pack("<I", 1)])
        self.assertEqual(extra.values(b"DATA"), [b"\x06"])
        self.assertEqual(extra.values(b"PNAM"), [struct.pack("<I", 0)])
        remapped = remap(primary, {1: 3})
        self.assertEqual(remapped.form_id, (3 << 24) | (EMPTY_HEAD_ID & 0xFFFFFF))
        from build_npc import ARMOR_ID, appearance_records
        armor_recs, _ = appearance_records(settings, None, facial=facial)
        armor = next(r for r in armor_recs if r.form_id == ARMOR_ID)
        bod2_mask = struct.unpack_from("<I", armor.values(b"BOD2")[0], 0)[0]
        self.assertEqual(bod2_mask & 1, 0)  # Slot 30 (HEAD) must not be occupied when facial HeadParts are active
        static_recs, _ = appearance_records(settings, None, facial=None)
        static_armor = next(r for r in static_recs if r.form_id == ARMOR_ID)
        self.assertEqual(struct.unpack_from("<I", static_armor.values(b"BOD2")[0], 0)[0] & 1, 1)


if __name__ == "__main__":
    unittest.main()
