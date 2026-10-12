"""Prepare local game armor and a body-conditioned deformation for Blender."""
import hashlib
import json
import logging
from pathlib import Path
import struct
import subprocess

import numpy as np
from scipy.spatial import cKDTree

from armor_geometry import BodyField, canonical_bone, canonical_weights
from armor_catalog import HUMAN_SLOTS, head_policy, official_choices, partition_slot, slot_mask, native_partition
from game_assets import GameAssets
from custom_skeleton import NifFile, matrix
from official_catalog import OfficialCatalog
from settings import load_settings, reference_root

LOG = logging.getLogger(__name__)
BODY_SLOTS = {32, 33, 34, 37, 38}


def world_vertices(shape):
    transform = matrix(shape.transform)
    return np.asarray(shape.verts) @ transform[:3, :3].T + transform[:3, 3]


def skin_shape(shape):
    # Compare actual skin texture paths; a shape name is not a reliable contract.
    texture = shape.textures.get("Diffuse", "").lower().replace("\\", "/")
    return "/actors/character/" in texture and any(x in texture for x in ("body_", "hands_", "feet_", "head_", "femalehead.", "malehead."))


def mesh_data(path):
    result = []
    with NifFile(str(path)) as nif:
        parents = {name: node.parent.name if node.parent else None for name, node in nif.nodes.items()}
        for index, shape in enumerate(nif.shapes):
            result.append({"name": shape.name, "index": index, "points": world_vertices(shape),
                           "tris": np.asarray(shape.tris, dtype=int), "weights": shape.bone_weights,
                           "skin": skin_shape(shape), "textures": shape.textures,
                           "partitions": np.array([shape.partitions[i].id for i in shape.partition_tris], dtype=int),
                           "parents": parents})
    return result


def combine(parts, parents):
    points, tris, partitions, weights, offset = [], [], [], {}, 0
    for part in parts:
        points.append(part["points"])
        tris.append(part["tris"] + offset)
        partitions.append(part["partitions"])
        # Mesh NIFs flatten skin bones under a scene root. The real reference
        # skeleton owns hierarchy, including twists/fingers and proxy offsets.
        for name, pairs in canonical_weights(part["weights"], {**part["parents"], **parents}).items():
            weights.setdefault(name, []).extend((i + offset, w) for i, w in pairs)
        offset += len(part["points"])
    return np.concatenate(points), np.concatenate(tris), np.concatenate(partitions), weights


def fit(output, game_data, blender, skin_only=False):
    """Called after original conversion; modifies only the new output folder."""
    output, game_data = Path(output).resolve(), Path(game_data).resolve()
    settings = load_settings(output)
    if not settings.fitting_enabled and not skin_only:
        return
    catalog = OfficialCatalog(game_data)
    refs = reference_root(output)
    work = output / "armor-source"
    work.mkdir(exist_ok=True)
    assets = GameAssets(game_data, catalog.plugins, work, settings.fit_source == 'installed')
    extract = assets.extract

    prefix = "female" if settings.sex == "female" else "male"
    reference_files = [extract(f'actors/character/character assets/{prefix}{part}_1.nif') for part in ('body', 'hands', 'feet')]
    source_parts = [p for file in reference_files for p in mesh_data(file) if p['skin']]
    original_body = output / "mod/meshes" / settings.asset_dir / "body.nif"
    target_parts = mesh_data(work / "body.nif" if (work / "body.nif").exists() else original_body)
    skeleton = original_body.parent / "skeleton.nif"
    skeleton_name = ('actors/character/character assets female/skeleton_female.nif'
                     if settings.sex == 'female' else 'actors/character/character assets/skeleton.nif')
    source_skeleton = extract(skeleton_name) if settings.fit_source == 'installed' else refs / ('meshes/' + skeleton_name)
    reference_signature = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest()
                                         for p in [*reference_files, source_skeleton, skeleton])).hexdigest()
    with NifFile(str(source_skeleton)) as source, NifFile(str(skeleton)) as target:
        parents = {n: node.parent.name if node.parent else None for n, node in source.nodes.items()}
        target_parents = {n: node.parent.name if node.parent else None for n, node in target.nodes.items()}
        source_joints = {n: matrix(node.global_transform)[:3, 3] for n, node in source.nodes.items()}
        target_joints = {n: matrix(node.global_transform)[:3, 3] for n, node in target.nodes.items()}
        target_transforms = {n: matrix(node.global_transform) for n, node in target.nodes.items()}
    src, src_tris, src_slots, src_weights = combine(source_parts, parents)
    dst, dst_tris, _, dst_weights = combine(target_parts, target_parents)
    field = BodyField(src, src_weights, dst, dst_weights, source_joints, target_joints)
    conformed = field.deform(src, src_weights)
    reference_centers = conformed[src_tris].mean(axis=1)
    nearest_reference = cKDTree(reference_centers).query(dst[dst_tris].mean(axis=1))[1]
    body_slots = src_slots[nearest_reference]
    if not {32, 33, 37}.issubset(set(body_slots)):
        raise ValueError("Target body cannot be separated into torso, hands and feet")
    plan = {"source_skeleton": str(source_skeleton), "body": [], "equipment": [], "bindings": [], "textures": {},
            'source_profile': settings.fit_source, 'reference_signature': reference_signature,
            'plugins': catalog.plugins, 'missing_optional_textures': []}
    arrays = {"reference": conformed, "target": dst}
    offset = 0
    for part in target_parts:
        plan["body"].append({"name": part["name"], "face_slots": body_slots[offset:offset + len(part["tris"])].tolist()})
        offset += len(part["tris"])
    selected = [] if skin_only else official_choices(catalog, settings.sex)
    if not skin_only and settings.fit_mode != 'all_official':
        allowed = {r.form_id for r in selected}
        selected = [catalog.require(key, b'ARMO') for key in settings.fit_armors]
        if any(r.form_id not in allowed for r in selected):
            raise ValueError('Selected equipment is not playable humanoid gear')
    needs_head = any(slot_mask(a) & ((1 << 0) | (1 << 1) | (1 << 12) | (1 << 13))
                     for r in selected for a in catalog.addon_records(r, settings.sex))
    if needs_head:
        head_source = mesh_data(extract(f'actors/character/character assets/{prefix}head.nif'))
        target_head_path = original_body.parent / 'face.nif'
        if not target_head_path.is_file():
            raise ValueError('Headgear requires classification of the VRM face mesh')
        head_target = mesh_data(target_head_path)
        head_src, _, _, head_src_weights = combine(head_source, parents)
        head_dst, _, _, head_dst_weights = combine(head_target, target_parents)
        combined_weights = {bone: list(pairs) for bone, pairs in src_weights.items()}
        for bone, pairs in head_src_weights.items():
            combined_weights.setdefault(bone, []).extend((i+len(src), w) for i, w in pairs)
        combined_target = {bone: list(pairs) for bone, pairs in dst_weights.items()}
        for bone, pairs in head_dst_weights.items():
            combined_target.setdefault(bone, []).extend((i+len(dst), w) for i, w in pairs)
        full_field = BodyField(np.concatenate((src, head_src)), combined_weights,
                               np.concatenate((dst, head_dst)), combined_target, source_joints, target_joints)
    else:
        full_field = field
    target_tree = cKDTree(dst)
    source_tree = cKDTree(src)
    target_vertex_weights = [{} for _ in dst]
    offset = 0
    for part in target_parts:
        for bone, pairs in part["weights"].items():
            for i, w in pairs:
                target_vertex_weights[i + offset][bone] = w
        offset += len(part["points"])
    source_vertex_weights = [{} for _ in src]
    for bone, pairs in src_weights.items():
        for i, w in pairs:
            source_vertex_weights[i][bone] = w
    bindings = [(armor, addon) for armor in selected for addon in catalog.addon_records(armor, settings.sex)]
    unique = {}
    for armor, addon in bindings:
        key = catalog.key(addon)
        origin, local = catalog.identity(armor)
        policy = head_policy(settings, addon, key)
        binding = {'editor_id': armor.editor_id, 'original_form_id': armor.form_id,
                   'origin_plugin': origin, 'origin_local_id': local, 'armor_mask': slot_mask(armor),
                   'source_addon_key': key, **policy}
        if key not in unique:
            unique[key] = len(unique)
        binding['mesh_index'] = unique[key]
        plan['bindings'].append(binding)
    LOG.info('Batch fitting %s items / %s humanoid addons', len(selected), len(unique))
    for key, item_index in unique.items():
        addon = catalog.require(key, b'ARMA')
        binding = next(i for i in plan['bindings'] if i['mesh_index'] == item_index)
        editor_id = binding['editor_id']
        tag = catalog.model_tag(addon, settings.sex)
        source_path = extract(addon.values(tag)[0].rstrip(b"\0").decode("utf8"))
        data = mesh_data(source_path)
        alternates = addon.values(b'MO3S' if tag == b'MOD3' else b'MO2S')
        texture_overrides = {}
        if alternates:
            blob = alternates[0]
            offset = 4
            for _ in range(struct.unpack_from('<I', blob)[0]):
                length = struct.unpack_from('<I', blob, offset)[0]
                offset += 4
                name = blob[offset:offset+length].rstrip(b'\0').decode('utf8')
                offset += length
                form_id, index = struct.unpack_from('<II', blob, offset)
                offset += 8
                texture_set = catalog.by_id[form_id]
                part = next((p for p in data if p['name'].casefold() == name.casefold()), None)
                if part is None:
                    part = next((p for p in data if p['index'] == index), None)
                    if part is None:
                        raise ValueError(f'Alternate-texture shape missing: {name} ({index})')
                    LOG.info('Alternate texture uses its 3D index: %s -> %s', name, part['name'])
                for tag_name, texture_name in ((b'TX00', 'Diffuse'), (b'TX01', 'Normal'), (b'TX02', 'SoftLighting'),
                                               (b'TX03', 'HeightMap'), (b'TX04', 'EnvMap'), (b'TX05', 'EnvMask'),
                                               (b'TX06', 'FacegenDetail'), (b'TX07', 'Specular')):
                    if texture_set.values(tag_name):
                        texture = texture_set.values(tag_name)[0].rstrip(b'\0').decode('utf8')
                        part['textures'][texture_name] = texture
                        texture_overrides.setdefault(part['name'], {})[texture_name] = texture
        exposed = [part for part in data if part["skin"]]
        source_centers = src[src_tris].mean(axis=1)
        if exposed:
            exposed_centers = np.concatenate([p["points"][p["tris"]].mean(axis=1) for p in exposed])
            exposed_distance = cKDTree(exposed_centers).query(source_centers)[0]
            visible = exposed_distance[nearest_reference] < 1.4
        else:
            visible = np.zeros(len(dst_tris), dtype=bool)
        mask = slot_mask(addon)
        slots = [s for s in sorted(HUMAN_SLOTS) if mask & 1 << (s - 30)]
        if not slots:
            raise ValueError(f"Unsupported addon partitions: {editor_id}")
        for part in data:
            if not part['skin']:
                part['partitions'] = np.array([native_partition(n, slots[0]) for n in part['partitions']], dtype=int)
        slots = sorted(set(slots) | {partition_slot(int(n), slots[0]) for p in data if not p['skin'] for n in p['partitions']})
        token = hashlib.sha256((key+settings.sex+settings.fit_source+reference_signature+
                                hashlib.sha256(source_path.read_bytes()).hexdigest()).encode()).hexdigest()[:16]
        equipment = {**binding, 'mesh_index': item_index, 'source_key': token,
                     "addon_local_id": 0x1000 + item_index,
                     "file": f"fitted_{token}_1.nif", "slots": slots,
                     "source": str(source_path), "source_addon": addon.editor_id,
                     "priority": addon.values(b"DNAM")[0][1 if settings.sex == "female" else 0],
                     "shapes": [], "exposed_body": [], 'texture_overrides': texture_overrides}
        LOG.info("Fitting %s: %s source shapes, %s embedded skin shapes", editor_id, len(data), len(exposed))
        for part in data:
            if part["skin"]:
                continue
            weights = {}
            # Extra skirt/pauldron bones may lack a humanoid ancestor. Their
            # skin follows the nearest original body rather than an invented rig.
            unknown = set()
            for bone, pairs in part["weights"].items():
                try:
                    target_bone = canonical_bone(bone, {**part["parents"], **parents})
                except ValueError:
                    unknown.add(bone)
                    for i, weight in pairs:
                        reference = source_tree.query(part["points"][i])[1]
                        for target_bone, value in source_vertex_weights[reference].items():
                            weights.setdefault(target_bone, []).append((i, weight * value))
                else:
                    weights.setdefault(target_bone, []).extend(pairs)
            fitting_field = full_field if set(slots) & {30, 31, 41, 42, 43} else field
            if not part['weights']:
                bone = 'SHIELD' if 39 in slots else ('NPC R Finger11 [RF11]' if 36 in slots else 'NPC Spine2 [Spn2]')
                if bone not in source_joints or bone not in target_joints:
                    raise ValueError(f'Rigid attachment bone missing: {bone}')
                transform = target_transforms[bone]
                points = part['points'] @ transform[:3, :3].T + transform[:3, 3]
                transferred = {bone: [(i, 1.) for i in range(len(points))]}
            else:
                points = fitting_field.deform(part["points"], weights)
                if binding['armor_mask'] & (1 << 6) and not binding['armor_mask'] & sum(1 << (s-30) for s in BODY_SLOTS):
                    # Keep finger weights; a ring must follow its finger, not the palm surface.
                    transferred = {b: pairs for b, pairs in part['weights'].items() if b in target_joints}
                elif set(slots) & {30, 31, 41, 42, 43} and not set(slots) & BODY_SLOTS:
                    transferred = {'NPC Head [Head]': [(i, 1.) for i in range(len(points))]}
                else:
                    _, near = target_tree.query(points)
                    transferred = {}
                    for index, vertex in enumerate(near):
                        for name, value in sorted(target_vertex_weights[vertex].items(), key=lambda x: -x[1])[:4]:
                            transferred.setdefault(name, []).append((index, value))
            key = f"equipment_{item_index}_{part['index']}"
            arrays[key] = points
            equipment["shapes"].append({"name": part["name"], "index": part["index"], "points": key,
                                         "weights": transferred, "face_slots": part["partitions"].tolist() if len(part['partitions']) else [slots[0]]*len(part['tris']),
                                         "remapped_auxiliary_bones": sorted(unknown)})
            for texture_slot, texture in part["textures"].items():
                if not texture or texture in plan["textures"]:
                    continue
                try:
                    texture_path = extract(texture, 'textures')
                except FileNotFoundError:
                    if texture_slot in ('Diffuse', 'Normal'):
                        raise
                    # Some shipping NIFs reference optional maps absent from the
                    # official archives. Preserve that lack of a map explicitly.
                    plan['textures'][texture] = ''
                    plan['missing_optional_textures'].append({'source': str(source_path), 'slot': texture_slot, 'texture': texture})
                    LOG.warning('Official optional texture is absent; leaving slot empty: %s (%s)', texture, texture_slot)
                    continue
                name = hashlib.sha256(texture.lower().encode()).hexdigest()[:12] + "_" + texture_path.name
                relative = f"textures/{settings.asset_dir}/equipment/{name}"
                dest = output / "mod" / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(texture_path.read_bytes())
                plan["textures"][texture] = relative
                decoded = output / "dds-preview"
                decoded.mkdir(exist_ok=True)
                command = [str(Path(__file__).parent / "dependencies/texconv.exe"), "-nologo", "-y", "-ft", "png", "-o", str(decoded), str(dest)]
                subprocess.run(command, check=True, capture_output=True)
        offset = 0
        for part in target_parts:
            count = len(part["tris"])
            faces = [i for i in range(count) if visible[offset + i] and body_slots[offset + i] in slots]
            equipment["exposed_body"].append({"name": part["name"], "faces": faces,
                                                "face_slots": body_slots[offset:offset + count].tolist()})
            offset += count
        plan["equipment"].append(equipment)
    np.savez_compressed(output / "armor-fit-arrays.npz", **arrays)
    (output / "armor-fit-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf8")
    # Keep the complete original body as the input to the partitioning stage.
    if not (work / "body.nif").exists():
        (work / "body.nif").write_bytes(original_body.read_bytes())
    from converter import run_blender
    run_blender(blender, "fit_armor_blender.py", ["--output", output, *(['--skin-only'] if skin_only else [])], output, "Fit armor")
