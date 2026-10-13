"""Validate the delivered NIF, textures and plugin, and decode DDS for rendering."""

import argparse
import json
import logging
import locale
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from scipy.spatial import cKDTree

from plugin import records
from settings import load_settings
from build_npc import NPC_ID, RACE_ID
from wardrobe import components, equip_slots, keyword_names, skin_components
from gear_head_runtime import head_variants, validate_head_models
from head_visibility import validate_head_visibility
from equipment_runtime import runtime_records, vmad, script_name, pex_strings, PROPERTIES
from nif_materials import DOUBLE_SIDED
from dds import validate_dds
from clothing_validation import validate_clothing_skin

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies/io_scene_nifly"))
from pyn.pynifly import NifFile  # noqa: E402 - isolated native-library import


def validate(output, skeleton=None):
    output = Path(output).resolve()
    mod = output / "mod"
    settings = load_settings(output)
    if settings.physics_enabled:
        from fsmp import validate_physics
        validate_physics(output)
    skeleton = mod / "meshes" / settings.asset_dir / "skeleton.nif"
    with NifFile(str(skeleton)) as reference:
        bone_set = set(reference.nodes)
    shapes = []
    textures = set()
    delivered_points = []
    manifest = (
        json.loads((output / "appearance.json").read_text(encoding="utf8"))
        if (output / "appearance.json").exists()
        else {"components": components(settings)}
    )
    component_reports = []
    baseline = np.load(output / "source-posed-vertices.npz")
    for part in manifest["components"]:
        part_points, part_shapes = [], []
        with NifFile(str(mod / "meshes" / settings.asset_dir / part["file"])) as nif:
            if nif.game != "SKYRIMSE":
                raise ValueError(f"Wrong NIF target: {nif.game}")
            for shape in nif.shapes:
                if settings.physics_enabled and shape.name == 'V2SCollision_Body':
                    continue  # Checked separately by validate_physics, never rendered.
                if part.get('retained_skin') and shape.name.startswith('V2SClothingSkin_'):
                    continue  # Validated against the partitioned original skin below, not counted twice.
                source_shape = next((s for s in part.get('shapes', []) if s['name'] == shape.name), None)
                if source_shape is not None and 'double_sided' in source_shape:
                    if bool(shape.shader.properties.Shader_Flags_2 & DOUBLE_SIDED) != source_shape['double_sided']:
                        raise ValueError('NIF face culling differs from source material: '+shape.name)
                if len(shape.verts) > 65535 or not shape.bone_names:
                    raise ValueError(f"Invalid skinned shape: {shape.name}")
                if set(shape.bone_names) - bone_set:
                    raise ValueError(
                        f"Bones missing from the NPC skeleton: {set(shape.bone_names) - bone_set}"
                    )
                delivered_points.append(np.array(shape.verts))
                part_points.append(np.array(shape.verts))
                if settings.armor_support and not {
                    partition.id for partition in shape.partitions
                }.issubset(set(part.get("slots", [part["slot"]]))):
                    raise ValueError(
                        f"NIF partition does not match component slot: {shape.name}"
                    )
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
                if not shape.shader.textures.get(
                    "Diffuse"
                ) or not shape.shader.textures.get("Normal"):
                    raise ValueError(f"Missing diffuse or normal texture: {shape.name}")
                for texture in texture_paths:
                    relative = texture.replace("\\", "/")
                    path = (mod / relative).resolve()
                    if not path.is_relative_to(mod.resolve()) or not path.exists():
                        raise ValueError(f"Missing or external texture: {texture}")
                    textures.add(path)
                shapes.append(
                    {
                        "name": shape.name,
                        "vertices": len(shape.verts),
                        "component": part["id"],
                        "triangles": len(shape.tris),
                        "bones": shape.bone_names,
                        "max_influences": max(counts),
                        "textures": shape.shader.textures,
                        "alpha_flags": shape.alpha_property.properties.flags
                        if shape.has_alpha_property
                        else None,
                    }
                )
                part_shapes.append(shapes[-1])
        if settings.armor_support:
            expected = np.concatenate(
                [baseline[f"VRMNode_{node:05}"] for node in part["nodes"]]
            )
            observed = np.concatenate(part_points)
            error = float(cKDTree(expected).query(observed)[0].max())
            if not part.get("partial_source"):
                error = max(error, float(cKDTree(observed).query(expected)[0].max()))
            if error > 0.001:
                raise ValueError(
                    f"Separated component differs from its source nodes: {part['id']}: {error}"
                )
            component_reports.append(
                {
                    "id": part["id"],
                    "slot": part["slot"],
                    "source_pose_max_vertex_distance": error,
                    "shapes": len(part_shapes),
                    "triangles": sum(s["triangles"] for s in part_shapes),
                }
            )
    generated = list(records(mod / settings.plugin_name))
    head_visibility = validate_head_visibility(generated, settings)
    for path in (mod / 'meshes' / settings.asset_dir / 'native_head_empty.nif',
                 mod / 'meshes/actors/character/facegendata/facegeom' / settings.plugin_name / '00000800.nif'):
        with NifFile(str(path)) as native_head:
            if native_head.game != 'SKYRIMSE' or native_head.root.blockname != 'BSFadeNode' or native_head.shapes:
                raise ValueError('Native head/FaceGen contains renderable geometry or the wrong root')
    local_ids = {
        record.form_id for record in generated if record.kind not in (b"TES4", b"CELL")
    }
    expected_records = (
        9
        if not settings.armor_support
        else 9 + len(PROPERTIES)
        + len(skin_components(settings))
        + 2 * len(settings.appearance_parts["garments"])
        + (len({i['addon_local_id'] for i in json.loads((output/'armor-fitting.json').read_text())['equipment']})
           if settings.fitting_enabled else 0)
        + ((5 + sum(bool(p['nodes']) for p in head_variants(settings))) if settings.head_switch_enabled else 0)
    )
    if len(local_ids) != expected_records:
        raise ValueError(f"Expected {expected_records} private follower records")
    if any(form_id >> 24 != 1 for form_id in local_ids):
        raise ValueError("Plugin overrides an existing record")
    for record in generated:
        for tag, payload in record.fields:
            reference_tags = {b"ARMO": {b"MODL", b"RNAM"}, b"ARMA": {b"RNAM", b"MODL"},
                              b"NPC_": {b"DOFT", b"RNAM", b"WNAM", b"CNTO"},
                                b"RACE": {b"WNAM", b"HEAD"}, b"OTFT": {b"INAM"},
                                b"HDPT": {b"RNAM"}, b"FLST": {b"LNAM"}}
            if tag in reference_tags.get(record.kind, set()):
                if (tag == b"CNTO" and len(payload) != 8) or (tag != b"CNTO" and len(payload) % 4):
                    raise ValueError("Malformed plugin reference field")
                refs = (
                    [payload[:4]]
                    if tag == b"CNTO"
                    else [payload[i : i + 4] for i in range(0, len(payload), 4)]
                )
                for ref in refs:
                    value = struct.unpack("<I", ref)[0]
                    if value >> 24 == 1 and value not in local_ids:
                        raise ValueError("Dangling local record reference")
    by_name = {record.editor_id: record for record in generated}
    race = by_name[settings.prefix + "Race"]
    for name in (settings.prefix + "NPC", settings.prefix + "Appearance"):
        if by_name[name].values(b"RNAM") != [struct.pack("<I", race.form_id)]:
            raise ValueError(f"NPC/appearance does not reference private race: {name}")
    addons = [r for r in generated if r.kind == b"ARMA"]
    for addon in addons:
        if addon.values(b"RNAM") != [struct.pack("<I", RACE_ID)]:
            raise ValueError("Appearance addon uses another race")
        for tag in (b"MOD2", b"MOD3"):
            path = (
                mod
                / "meshes"
                / addon.values(tag)[0].rstrip(b"\0").decode("utf8").replace("\\", "/")
            )
            if not path.is_file():
                raise ValueError("Appearance addon mesh is missing")
    if settings.armor_support:
        by_id = {r.form_id: r for r in generated}
        keyword_manifest = json.loads((output/'npc.json').read_text(encoding='utf8'))['garment_keywords']
        skin = by_name[settings.prefix + "Appearance"]
        expected_skin = skin_components(settings)
        if len(skin.values(b"MODL")) != len(expected_skin):
            raise ValueError(
                "Skin does not contain all permanent appearance components"
            )
        for ref in skin.values(b"MODL"):
            if by_id[struct.unpack("<I", ref)[0]].kind != b"ARMA":
                raise ValueError("Skin references a non-addon")
        outfit_ids = set(
            struct.unpack(
                "<"
                + "I"
                * (len(by_name[settings.prefix + "Outfit"].values(b"INAM")[0]) // 4),
                by_name[settings.prefix + "Outfit"].values(b"INAM")[0],
            )
        )
        expected_outfit = set()
        for index, garment in enumerate(settings.appearance_parts["garments"]):
            item = by_name[settings.prefix + "Garment_" + garment["id"]]
            if item.form_id != 0x01000811 + garment.get('record_index', index) * 2:
                raise ValueError('Garment record ID changed during native wardrobe migration')
            expected_keywords = keyword_manifest[garment['id']]
            names = keyword_names(garment)
            if (list(expected_keywords) != names or item.values(b'KSIZ') != [struct.pack('<I', len(names))]
                    or item.values(b'KWDA') != [b''.join(struct.pack('<I', expected_keywords[n]) for n in names)]):
                raise ValueError('Garment usage/vendor keywords mismatch')
            if item.flags & 4 or item.values(b"FULL") != [
                garment["name"].encode("utf8") + b"\0"
            ]:
                raise ValueError("Garment is not a named wearable item")
            mask, kind = struct.unpack("<II", item.values(b"BOD2")[0])
            garment_slots = equip_slots(garment)
            if (
                mask != sum(1 << (slot - 30) for slot in garment_slots)
                or kind
                != {"light": 0, "heavy": 1, "clothing": 2}[garment["armor_type"]]
            ):
                raise ValueError("Garment slot/type mismatch")
            if struct.unpack("<i", item.values(b"DNAM")[0])[0] != round(
                garment["armor_rating"] * 100
            ):
                raise ValueError("Garment armor rating mismatch")
            npc = by_name[settings.prefix + 'NPC']
            if struct.pack('<Ii', item.form_id, 1) not in npc.values(b'CNTO'):
                raise ValueError('Garment missing from ordinary follower inventory')
        if outfit_ids != expected_outfit or skin.form_id in outfit_ids:
            raise ValueError(
                "Wardrobe default outfit must be empty, with clothes in ordinary inventory"
            )
        if npc.values(b'VMAD') != [vmad(settings)]:
            raise ValueError('Wardrobe script properties do not match the follower')
        _, _, _, strings = pex_strings((mod/'scripts'/(script_name(settings)+'.pex')).read_bytes())
        if script_name(settings).encode() not in strings:
            raise ValueError('Wardrobe PEX does not declare the private script name')
        if {s.lower() for s in strings} & {b'unequipitem', b'setoutfit', b'removeitem', b'additem', b'queueninodeupdate'}:
            raise ValueError('Native wardrobe PEX still contains a scripted replacement/inventory mutation')
        fitting_profile = json.loads((output/'armor-fitting.json').read_text()) if settings.fitting_enabled else None
        for expected in runtime_records(settings, profile=fitting_profile):
            if by_id[expected.form_id].fields != expected.fields:
                raise ValueError('Wardrobe replacement group differs from its configured garments/equipment')
    if (
        race.values(b"ANAM")
        != [(settings.asset_dir.replace("/", "\\") + "\\skeleton.nif\0").encode()] * 2
    ):
        raise ValueError("Private race references the wrong skeleton")
    npc = by_name[settings.prefix + "NPC"]
    if npc.form_id != NPC_ID or race.form_id != RACE_ID:
        raise ValueError("Wrong follower/race IDs")
    if npc.values(b"FULL") != [settings.npc_name.encode("utf8") + b"\0"]:
        raise ValueError("NPC name was not written to the plugin")
    factions = {
        struct.unpack_from("<I", value)[0]: struct.unpack_from("<b", value, 4)[0]
        for value in npc.values(b"SNAM")
    }
    if factions.get(0x5C84D) != 0 or factions.get(0x5C84E) != -1:
        raise ValueError("Follower recruitment factions/ranks missing")
    relation = by_name[settings.prefix + "PlayerRelationship"]
    if struct.unpack("<IIHBBI", relation.values(b"DATA")[0]) != (NPC_ID, 7, 1, 0, 0, 0):
        raise ValueError("Player ally relationship missing")
    actor = by_name[settings.prefix + "FollowerREF"]
    if actor.values(b"NAME") != [struct.pack("<I", NPC_ID)] or not actor.flags & 0x400:
        raise ValueError("Persistent placed follower missing")
    if actor.groups[-2:] != (
        (struct.pack("<I", 0x165A7), 6),
        (struct.pack("<I", 0x165A7), 8),
    ):
        raise ValueError("Follower is outside the Temple of Kynareth")
    if {record.form_id for record in generated if record.kind == b"CELL"} != {0x165A7}:
        raise ValueError("Unexpected existing cell override")
    original = np.concatenate([baseline[name] for name in baseline.files])
    delivered = np.concatenate(delivered_points)
    forward = cKDTree(original).query(delivered)[0]
    reverse = cKDTree(delivered).query(original)[0]
    error = float(max(forward.max(), reverse.max()))
    if error > 0.001:
        raise ValueError(
            f"Delivered NIF differs from the original VRM posed without stretch: {error}"
        )
    preview = output / "dds-preview"
    preview.mkdir(exist_ok=True)
    texture_reports = []
    for texture in sorted(textures):
        texture_reports.append({'path': texture.relative_to(mod).as_posix(), **validate_dds(texture)})
        command = [
            str(ROOT / "dependencies/texconv.exe"),
            "-nologo",
            "-y",
            "-ft",
            "png",
            "-o",
            str(preview),
            str(texture),
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding=locale.getencoding(), errors='replace')
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    report = {
        "nif_shapes": shapes,
        "total_triangles": sum(shape["triangles"] for shape in shapes),
        "textures_resolved": len(textures),
        "texture_headers": texture_reports,
        "new_plugin_records": len(local_ids),
        "source_pose_max_vertex_distance": error,
        "private_skeleton_nodes": len(bone_set),
        "components": component_reports,
        "game_verified": False,
        "head_visibility": head_visibility,
        'head_models': validate_head_models(output, settings),
        'clothing_skin': validate_clothing_skin(output, settings),
    }
    (output / "validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    logging.info(
        "Validated: %s NIF shapes, %s triangles, %s textures, %s new records",
        len(shapes),
        report["total_triangles"],
        len(textures),
        len(local_ids),
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--skeleton", type=Path)
    args = parser.parse_args()
    validate(args.output, args.skeleton)
