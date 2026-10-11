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


if __name__ == "__main__":
    unittest.main()
