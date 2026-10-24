"""Validate the delivered NIF, textures and plugin, and decode DDS for rendering."""

import argparse
import json
import logging
from pathlib import Path
import struct
import sys

import numpy as np
from scipy.spatial import cKDTree
from textures import decode_dds

from follower_plugin import follower_records
from settings import load_settings
from build_npc import NPC_ID, RACE_ID
from wardrobe import components, equip_slots, keyword_names, skin_components, nif_partition
from gear_head_runtime import validate_head_models
from head_visibility import validate_head_visibility
from equipment_runtime import runtime_records, vmad, script_name, pex_strings
from nif_materials import DOUBLE_SIDED, validate_alpha_order
from dds import validate_dds
from clothing_validation import validate_clothing_skin
from plugin_validation import validate_private_records

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies/io_scene_nifly"))
from pyn.pynifly import NifFile  # noqa: E402 - isolated native-library import


def validate(output, skeleton=None):
    output = Path(output).resolve()
    mod = output / "mod"
    settings = load_settings(output)
    outlines = set()
    if settings.toon_enabled:
        from toon import validate_toon
        validate_toon(output)
        toon_report = json.loads((output/'toon.json').read_text(encoding='utf8'))
        outlines = {(e['file'], e['shape']) for e in toon_report['materials'] if e.get('role') == 'outline'}
    if settings.physics_enabled:
        from fsmp import validate_physics, PROXY, ARM_PROXY, SECONDARY_PROXY
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
            policies = {s['name']: s['material_policy'] for s in part.get('shapes', []) if 'material_policy' in s}
            if policies:
                validate_alpha_order(nif, policies)
            for shape in nif.shapes:
                if (part['file'], shape.name) in outlines:
                    continue  # Owner, topology, skin and marker were verified by validate_toon.
                if settings.physics_enabled and shape.name in {PROXY, ARM_PROXY, SECONDARY_PROXY}:
                    continue  # Checked separately by validate_physics, never rendered.
                if part.get('retained_skin') and shape.name.startswith('V2SClothingSkin_'):
                    continue  # Validated against the partitioned original skin below, not counted twice.
                source_shape = next((s for s in part.get('shapes', []) if s['name'] == shape.name), None)
                if source_shape is not None and 'double_sided' in source_shape:
                    if bool(shape.shader.properties.Shader_Flags_2 & DOUBLE_SIDED) != source_shape['double_sided']:
                        raise ValueError('NIF face culling differs from source material: '+shape.name)
                if source_shape is not None and 'diffuse' in source_shape:
                    if shape.textures.get('Diffuse', '').replace('\\', '/').lower() != source_shape['diffuse'].lower():
                        raise ValueError('NIF diffuse differs from original material bake: '+shape.name)
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
                }.issubset({nif_partition(s) for s in part.get("slots", [part["slot"]])}):
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
    generated = follower_records(mod / settings.plugin_name)
    head_visibility = validate_head_visibility(generated, settings)
    for path in (mod / 'meshes' / settings.asset_dir / 'native_head_empty.nif',
                 mod / 'meshes/actors/character/facegendata/facegeom' / settings.plugin_name / '00000800.nif'):
        with NifFile(str(path)) as native_head:
            if native_head.game != 'SKYRIMSE' or native_head.root.blockname != 'BSFadeNode' or native_head.shapes:
                raise ValueError('Native head/FaceGen contains renderable geometry or the wrong root')
    local_ids = validate_private_records(generated, settings, output)
    by_name = {record.editor_id: record for record in generated}
    npc = by_name[settings.prefix + 'NPC']
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
        expected_vmad = vmad(settings)
        if settings.sitting_enabled:
            from seating import append_binding
            seat_report = json.loads((output / 'seating.json').read_text(encoding='utf8'))
            expected_vmad = append_binding(expected_vmad, settings, seat_report['offset'])
        if npc.values(b'VMAD') != [expected_vmad]:
            raise ValueError('Wardrobe script properties do not match the follower')
        _, _, _, strings = pex_strings((mod/'scripts'/(script_name(settings)+'.pex')).read_bytes())
        if script_name(settings).encode() not in strings:
            raise ValueError('Wardrobe PEX does not declare the private script name')
        if {s.lower() for s in strings} & {b'unequipitem', b'setoutfit', b'removeitem', b'additem', b'queueninodeupdate'}:
            raise ValueError('Native wardrobe PEX still contains a scripted replacement/inventory mutation')
        fitting_profile = json.loads((output/'armor-fitting.json').read_text()) if settings.fitting_enabled else None
        if settings.head_switch_enabled:
            from gear_head_runtime import IDS
            for name, flag in (('FaceHidingEquipment', 'hide_face'), ('HairHidingEquipment', 'hide_hair')):
                actual = {struct.unpack('<I', v)[0] for v in by_id[IDS[name]].values(b'LNAM')}
                own = {0x01000811 + 2 * g.get('record_index', i)
                       for i, g in enumerate(settings.appearance_parts['garments']) if g.get(flag, False)}
                if {v for v in actual if v >> 24 == 1} != own:
                    raise ValueError('Original headwear visibility list differs from configured ARMO items')
        for expected in runtime_records(settings, profile=fitting_profile):
            if by_id[expected.form_id].fields != expected.fields:
                raise ValueError('Wardrobe replacement group differs from its configured garments/equipment')
    if (
        race.values(b"ANAM")
        != [(settings.asset_dir.replace("/", "\\") + "\\skeleton.nif\0").encode()] * 2
    ):
        raise ValueError("Private race references the wrong skeleton")
    npc = by_name[settings.prefix + "NPC"]
    if settings.sitting_enabled:
        from seating import validate_runtime
        validate_runtime(output, settings, npc, {r.form_id: r for r in generated})
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
    weapon_report = None
    if settings.weapon_mode == 'original':
        from weapon import check_bounds, validate_weapon_model
        weapon_report, weapon_textures = validate_weapon_model(output, settings)
        check_bounds(generated, weapon_report['bounds'])
        textures |= weapon_textures
    preview = output / "dds-preview"
    preview.mkdir(exist_ok=True)
    texture_reports = []
    for texture in sorted(textures):
        texture_reports.append({'path': texture.relative_to(mod).as_posix(), **validate_dds(texture)})
        decode_dds(texture, preview)
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
        'original_weapon': weapon_report,
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
