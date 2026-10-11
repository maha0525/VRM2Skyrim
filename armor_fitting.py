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
from armor_catalog import equipment_choices, slot_mask
from bsa import BSA
from custom_skeleton import NifFile, matrix
from game_catalog import GameCatalog
from settings import load_settings, reference_root

LOG = logging.getLogger(__name__)
BODY_SLOTS = {32, 33, 34, 37, 38}


def world_vertices(shape):
    transform = matrix(shape.transform)
    return np.asarray(shape.verts) @ transform[:3, :3].T + transform[:3, 3]


def skin_shape(shape):
    # Compare actual skin texture paths; a shape name is not a reliable contract.
    texture = shape.textures.get("Diffuse", "").lower().replace("\\", "/")
    return "/actors/character/" in texture and any(x in texture for x in ("body_", "hands_", "feet_"))


def mesh_data(path):
    result = []
    with NifFile(str(path)) as nif:
        parents = {name: node.parent.name if node.parent else None for name, node in nif.nodes.items()}
        for index, shape in enumerate(nif.shapes):
            result.append({"name": shape.name, "index": index, "points": world_vertices(shape),
                           "tris": np.asarray(shape.tris, dtype=int), "weights": shape.bone_weights,
                           "skin": skin_shape(shape), "textures": shape.textures,
                           "partitions": np.array([shape.partitions[i].id for i in shape.partition_tris]),
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


def fit(output, game_data, blender):
    """Called after original conversion; modifies only the new output folder."""
    output, game_data = Path(output).resolve(), Path(game_data).resolve()
    settings = load_settings(output)
    if not settings.fit_armors:
        return
    catalog = GameCatalog(game_data)
    refs = reference_root(output)
    work = output / "armor-source"
    work.mkdir(exist_ok=True)
    archives = {}

    def extract(name, kind="meshes"):
        name = name.lower().replace("\\", "/")
        if not name.startswith(kind + "/"):
            name = kind + "/" + name
        dest = work / name
        if dest.exists():
            return dest
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe game asset path")
        archive_names = (["Skyrim - Meshes0.bsa", "Skyrim - Meshes1.bsa"] if kind == "meshes"
                         else [f"Skyrim - Textures{i}.bsa" for i in range(9)])
        for archive_name in archive_names:
            if not (game_data / archive_name).exists():
                continue
            if archive_name not in archives:
                archives[archive_name] = BSA(game_data / archive_name)
            archive = archives[archive_name]
            if name in archive.entries:
                archive.extract(name, dest)
                return dest
        raise FileNotFoundError(f"Game asset is not in the original BSAs: {name}")

    prefix = "female" if settings.sex == "female" else "male"
    source_parts = [p for part in ("body", "hands", "feet")
                    for p in mesh_data(extract(f"actors/character/character assets/{prefix}{part}_1.nif")) if p["skin"]]
    original_body = output / "mod/meshes" / settings.asset_dir / "body.nif"
    target_parts = mesh_data(work / "body.nif" if (work / "body.nif").exists() else original_body)
    skeleton = original_body.parent / "skeleton.nif"
    source_skeleton = refs / ("meshes/actors/character/character assets female/skeleton_female.nif"
                              if settings.sex == "female" else "meshes/actors/character/character assets/skeleton.nif")
    with NifFile(str(source_skeleton)) as source, NifFile(str(skeleton)) as target:
        parents = {n: node.parent.name if node.parent else None for n, node in source.nodes.items()}
        target_parents = {n: node.parent.name if node.parent else None for n, node in target.nodes.items()}
        source_joints = {n: matrix(node.global_transform)[:3, 3] for n, node in source.nodes.items()}
        target_joints = {n: matrix(node.global_transform)[:3, 3] for n, node in target.nodes.items()}
    src, src_tris, src_slots, src_weights = combine(source_parts, parents)
    dst, dst_tris, _, dst_weights = combine(target_parts, target_parents)
    field = BodyField(src, src_weights, dst, dst_weights, source_joints, target_joints)
    conformed = field.deform(src, src_weights)
    reference_centers = conformed[src_tris].mean(axis=1)
    nearest_reference = cKDTree(reference_centers).query(dst[dst_tris].mean(axis=1))[1]
    body_slots = src_slots[nearest_reference]
    if not {32, 33, 37}.issubset(set(body_slots)):
        raise ValueError("Target body cannot be separated into torso, hands and feet")
    plan = {"source_skeleton": str(source_skeleton), "body": [], "equipment": [], "textures": {}}
    arrays = {"reference": conformed, "target": dst}
    offset = 0
    for part in target_parts:
        plan["body"].append({"name": part["name"], "face_slots": body_slots[offset:offset + len(part["tris"])].tolist()})
        offset += len(part["tris"])
    lookup = {r.form_id: r for r in catalog.choices(b"ARMA")}
    human_race = catalog.require("NakedTorso", b"ARMA").values(b"RNAM")[0]
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
    for item_index, editor_id in enumerate(settings.fit_armors):
        armor = catalog.require(editor_id, b"ARMO")
        if armor not in equipment_choices(catalog):
            raise ValueError(f"Only body, hand and foot equipment is supported: {editor_id}")
        candidates = [lookup[struct.unpack("<I", value)[0]] for value in armor.values(b"MODL")]
        tag = b"MOD3" if settings.sex == "female" else b"MOD2"
        selected = [a for a in candidates if a.values(tag) and slot_mask(a) & slot_mask(armor)
                    and a.values(b"RNAM") == [human_race]]
        if len(selected) != 1:
            raise ValueError(f"Equipment needs one humanoid addon: {editor_id}")
        addon = selected[0]
        source_path = extract(addon.values(tag)[0].rstrip(b"\0").decode("utf8"))
        data = mesh_data(source_path)
        exposed = [part for part in data if part["skin"]]
        source_centers = src[src_tris].mean(axis=1)
        if exposed:
            exposed_centers = np.concatenate([p["points"][p["tris"]].mean(axis=1) for p in exposed])
            exposed_distance = cKDTree(exposed_centers).query(source_centers)[0]
            visible = exposed_distance[nearest_reference] < 1.4
        else:
            visible = np.zeros(len(dst_tris), dtype=bool)
        mask = slot_mask(addon)
        slots = [s for s in sorted(BODY_SLOTS) if mask & 1 << (s - 30)]
        if not slots or mask & ~sum(1 << (s - 30) for s in BODY_SLOTS):
            raise ValueError(f"Unsupported addon partitions: {editor_id}")
        equipment = {"editor_id": editor_id, "original_form_id": armor.form_id, "addon_local_id": 0x880 + item_index,
                     "file": f"fitted_{editor_id.lower()}_1.nif", "slots": slots,
                     "source": str(source_path), "source_addon": addon.editor_id,
                     "priority": addon.values(b"DNAM")[0][1 if settings.sex == "female" else 0],
                     "shapes": [], "exposed_body": []}
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
            points = field.deform(part["points"], weights)
            _, near = target_tree.query(points)
            transferred = {}
            for index, vertex in enumerate(near):
                for name, value in sorted(target_vertex_weights[vertex].items(), key=lambda x: -x[1])[:4]:
                    transferred.setdefault(name, []).append((index, value))
            key = f"equipment_{item_index}_{part['index']}"
            arrays[key] = points
            equipment["shapes"].append({"name": part["name"], "index": part["index"], "points": key,
                                         "weights": transferred, "face_slots": part["partitions"].tolist(),
                                         "remapped_auxiliary_bones": sorted(unknown)})
            for texture in part["textures"].values():
                if not texture or texture in plan["textures"]:
                    continue
                texture_path = extract(texture, "textures")
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
    run_blender(blender, "fit_armor_blender.py", ["--output", output], output, "Fit armor")
