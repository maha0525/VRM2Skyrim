"""Validate the delivered NIF, textures and plugin, and decode DDS for rendering."""
import argparse
import json
import logging
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from scipy.spatial import cKDTree

from plugin import records
from settings import load_settings
from build_npc import NPC_ID, RACE_ID

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies/io_scene_nifly"))
from pyn.pynifly import NifFile  # noqa: E402 - isolated native-library import


def validate(output, skeleton=None):
    output = Path(output).resolve()
    mod = output / "mod"
    settings = load_settings(output)
    skeleton = mod / "meshes" / settings.asset_dir / "skeleton.nif"
    with NifFile(str(skeleton)) as reference:
        bone_set = set(reference.nodes)
    shapes = []
    textures = set()
    delivered_points = []
    with NifFile(str(mod / "meshes" / settings.asset_dir / "avatar.nif")) as nif:
        if nif.game != "SKYRIMSE":
            raise ValueError(f"Wrong NIF target: {nif.game}")
        for shape in nif.shapes:
            if len(shape.verts) > 65535 or not shape.bone_names:
                raise ValueError(f"Invalid skinned shape: {shape.name}")
            if set(shape.bone_names) - bone_set:
                raise ValueError(f"Bones missing from the NPC skeleton: {set(shape.bone_names) - bone_set}")
            delivered_points.append(np.array(shape.verts))
            sums = [0.0] * len(shape.verts)
            counts = [0] * len(shape.verts)
            for _, pairs in shape.bone_weights.items():
                for vertex, weight in pairs:
                    sums[vertex] += weight
                    counts[vertex] += 1
            if any(count == 0 or count > 4 for count in counts):
                raise ValueError(f"Invalid bone influence count: {shape.name}")
            if max(abs(value - 1.0) for value in sums) > 0.015:
                raise ValueError(f"Unnormalized weights: {shape.name}")
            texture_paths = list(shape.shader.textures.values())
            if not shape.shader.textures.get("Diffuse") or not shape.shader.textures.get("Normal"):
                raise ValueError(f"Missing diffuse or normal texture: {shape.name}")
            for texture in texture_paths:
                relative = texture.replace("\\", "/")
                path = (mod / relative).resolve()
                if not path.is_relative_to(mod.resolve()) or not path.exists():
                    raise ValueError(f"Missing or external texture: {texture}")
                textures.add(path)
            shapes.append({"name": shape.name, "vertices": len(shape.verts),
                           "triangles": len(shape.tris), "bones": shape.bone_names,
                           "max_influences": max(counts), "textures": shape.shader.textures,
                           "alpha_flags": shape.alpha_property.properties.flags if shape.has_alpha_property else None})
    generated = list(records(mod / settings.plugin_name))
    local_ids = {record.form_id for record in generated if record.kind not in (b"TES4", b"CELL")}
    if len(local_ids) != 7:
        raise ValueError("Expected seven private follower records")
    if any(form_id >> 24 != 1 for form_id in local_ids):
        raise ValueError("Plugin overrides an existing record")
    for record in generated:
        for tag, payload in record.fields:
            if tag in (b"DOFT", b"MODL", b"INAM", b"RNAM", b"WNAM") and len(payload) == 4:
                value = struct.unpack("<I", payload)[0]
                if value >> 24 == 1 and value not in local_ids:
                    raise ValueError("Dangling local record reference")
    by_name = {record.editor_id: record for record in generated}
    race = by_name[settings.prefix + "Race"]
    for name in (settings.prefix + "NPC", settings.prefix + "Appearance", settings.prefix + "AppearanceAA"):
        if by_name[name].values(b"RNAM") != [struct.pack("<I", race.form_id)]:
            raise ValueError(f"NPC/appearance does not reference private race: {name}")
    if race.values(b"ANAM") != [(settings.asset_dir.replace("/", "\\") + "\\skeleton.nif\0").encode()] * 2:
        raise ValueError("Private race references the wrong skeleton")
    npc = by_name[settings.prefix + "NPC"]
    if npc.form_id != NPC_ID or race.form_id != RACE_ID:
        raise ValueError("Wrong follower/race IDs")
    if npc.values(b"FULL") != [settings.npc_name.encode("utf8") + b"\0"]:
        raise ValueError("NPC name was not written to the plugin")
    factions = {struct.unpack_from("<I", value)[0]: struct.unpack_from("<b", value, 4)[0]
                for value in npc.values(b"SNAM")}
    if factions.get(0x5C84D) != 0 or factions.get(0x5C84E) != -1:
        raise ValueError("Follower recruitment factions/ranks missing")
    relation = by_name[settings.prefix + "PlayerRelationship"]
    if struct.unpack("<IIHBBI", relation.values(b"DATA")[0]) != (NPC_ID, 7, 1, 0, 0, 0):
        raise ValueError("Player ally relationship missing")
    actor = by_name[settings.prefix + "FollowerREF"]
    if actor.values(b"NAME") != [struct.pack("<I", NPC_ID)] or not actor.flags & 0x400:
        raise ValueError("Persistent placed follower missing")
    if actor.groups[-2:] != ((struct.pack("<I", 0x165A7), 6), (struct.pack("<I", 0x165A7), 8)):
        raise ValueError("Follower is outside the Temple of Kynareth")
    if {record.form_id for record in generated if record.kind == b"CELL"} != {0x165A7}:
        raise ValueError("Unexpected existing cell override")
    baseline = np.load(output / "source-posed-vertices.npz")
    original = np.concatenate([baseline[name] for name in baseline.files])
    delivered = np.concatenate(delivered_points)
    forward = cKDTree(original).query(delivered)[0]
    reverse = cKDTree(delivered).query(original)[0]
    error = float(max(forward.max(), reverse.max()))
    if error > 0.001:
        raise ValueError(f"Delivered NIF differs from the original VRM posed without stretch: {error}")
    preview = output / "dds-preview"
    preview.mkdir(exist_ok=True)
    for texture in sorted(textures):
        command = [str(ROOT / "dependencies/texconv.exe"), "-nologo", "-y", "-ft", "png",
                   "-o", str(preview), str(texture)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    report = {"nif_shapes": shapes, "total_triangles": sum(shape["triangles"] for shape in shapes),
              "textures_resolved": len(textures), "new_plugin_records": len(local_ids),
              "source_pose_max_vertex_distance": error, "private_skeleton_nodes": len(bone_set),
              "game_verified": False}
    (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    logging.info("Validated: %s NIF shapes, %s triangles, %s textures, %s new records",
                 len(shapes), report["total_triangles"], len(textures), len(local_ids))
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--skeleton", type=Path)
    args = parser.parse_args()
    validate(args.output, args.skeleton)
