"""Read back equipment, original skin coverage, bindings and private addons."""
from collections import Counter
import json
import logging
from pathlib import Path
import struct

import numpy as np
from scipy.spatial import cKDTree

from custom_skeleton import NifFile
from follower_plugin import follower_records
from settings import load_settings
from armor_catalog import partition_slot, native_partition


def validate_fitting(output):
    output = Path(output).resolve()
    settings = load_settings(output)
    root = output / "mod/meshes" / settings.asset_dir
    profile = json.loads((output / "armor-fitting.json").read_text())
    plan = json.loads((output/'armor-fit-plan.json').read_text(encoding='utf8'))
    planned = {item['source_key']: item for item in plan['equipment']}
    points, triangles, offset = [], [], 0
    original_normals = {}
    with NifFile(str(output / "armor-source/body.nif")) as source:
        for shape in source.shapes:
            points.extend(shape.verts)
            triangles.extend(tuple(i + offset for i in face) for face in shape.tris)
            offset += len(shape.verts)
            key = shape.textures["Diffuse"].lower().replace("\\", "/")
            original_normals.setdefault(key, []).append((np.column_stack((shape.verts, shape.uvs)), np.asarray(shape.normals)))
    normal_references = {}
    for key, parts in original_normals.items():
        normal_references[key] = (cKDTree(np.concatenate([p[0] for p in parts])), np.concatenate([p[1] for p in parts]))

    def skin_normals(shape):
        key = shape.textures["Diffuse"].lower().replace("\\", "/")
        reference, normals = normal_references[key]
        distance, indices = reference.query(np.column_stack((shape.verts, shape.uvs)), k=min(12, len(normals)))
        if distance[:, 0].max() > .001:
            raise ValueError("Partitioned skin changed original UVs")
        # Coincident UV/position vertices may have different normals at seams or
        # on authored two-sided details. Match among those exact source corners.
        observed, expected = np.asarray(shape.normals)[:, None, :], normals[indices]
        denominator = np.linalg.norm(observed, axis=2) * np.linalg.norm(expected, axis=2)
        valid = denominator > 1e-6
        cosine = (observed * expected).sum(axis=2) / np.maximum(denominator, 1e-12)
        cosine[(distance > .001) | ~valid] = -2.
        minimum = float(cosine.max(axis=1).min())
        if minimum < .997:
            raise ValueError(f"Partitioned skin changed original shading normals: {shape.name}: {minimum}")
        return minimum
    points = np.asarray(points)
    tree = cKDTree(points)
    canonical = tree.query(points)[1]
    def triangle_key(indices):
        values = tuple(indices)
        return min(values, values[1:] + values[:1], values[2:] + values[:2])

    original_faces = Counter(triangle_key(canonical[list(face)]) for face in triangles)
    delivered_faces = Counter()
    normal_cosines = []
    for name in ("body.nif", "hands.nif", "feet.nif"):
        with NifFile(str(root / name)) as nif:
            for shape in nif.shapes:
                normal_cosines.append(skin_normals(shape))
                distance, indices = tree.query(shape.verts)
                if distance.max() > .001:
                    raise ValueError("Body fitting changed the original VRM skin vertices")
                delivered_faces.update(triangle_key(indices[list(face)]) for face in shape.tris)
    if delivered_faces != original_faces:
        raise ValueError("Body partitioning changed, lost or duplicated original skin faces")
    with NifFile(str(root / "skeleton.nif")) as skeleton:
        bones = set(skeleton.nodes)
    addons = {r.form_id & 0xFFFFFF: r for r in follower_records(output / "mod" / settings.plugin_name) if r.kind == b"ARMA"}
    result, cache = [], {}
    for item in profile["equipment"]:
        if item['addon_local_id'] in cache:
            result.append({**cache[item['addon_local_id']], 'editor_id': item['editor_id']})
            continue
        path = root / item["file"]
        if path.read_bytes() != path.with_name(path.name.replace("_1.nif", "_0.nif")).read_bytes():
            raise ValueError("Equipment weight variants must retain one original VRM body")
        addon = addons.get(item["addon_local_id"])
        if addon is None or addon.values(b"RNAM") != [struct.pack("<I", 0x01000804)]:
            raise ValueError("Fitted equipment addon does not reference the private race")
        if struct.unpack_from("<I", addon.values(b"BOD2")[0])[0] != sum(1 << (s - 30) for s in item["slots"]):
            raise ValueError("Fitted addon slot mismatch")
        count, exposed, maximum = 0, 0, 0.
        special_partitions = {}
        if set(item['slots']) & {30, 31, 41, 42, 43}:
            with NifFile(planned[item['source_key']]['source']) as original:
                for shape in original.shapes:
                    assigned = {native_partition(shape.partitions[i].id, item['slots'][0]) for i in shape.partition_tris}
                    if assigned & {130, 131, 141, 142, 143}:
                        special_partitions[f'Fitted_{shape.name}_'] = assigned
        observed_partitions = {prefix: set() for prefix in special_partitions}
        with NifFile(str(path)) as nif:
            if nif.game != "SKYRIMSE":
                raise ValueError("Fitted equipment is not an SE NIF")
            for shape in nif.shapes:
                for prefix, expected in special_partitions.items():
                    if shape.name.startswith(prefix):
                        observed = {p.id for p in shape.partitions}
                        if not observed.issubset(expected):
                            raise ValueError(f'Fitted headwear changed its original partition: {item["editor_id"]}/{shape.name}: {observed} vs {expected}')
                        observed_partitions[prefix].update(observed)
                if set(shape.bone_names) - bones or len(shape.verts) > 65535:
                    raise ValueError("Invalid fitted equipment bones or vertex count")
                if not {partition_slot(p.id, item['slots'][0]) for p in shape.partitions}.issubset(item["slots"]):
                    raise ValueError("Fitted equipment partition mismatch")
                totals = np.zeros(len(shape.verts))
                influences = np.zeros(len(shape.verts), dtype=int)
                for pairs in shape.bone_weights.values():
                    for index, value in pairs:
                        totals[index] += value
                        influences[index] += 1
                if np.any(influences < 1) or np.any(influences > 4) or np.max(np.abs(totals - 1)) > .015:
                    raise ValueError(f"Fitted equipment skin weights are invalid: {item['editor_id']}/{shape.name}; influences={int(influences.min())}..{int(influences.max())}, totals={float(totals.min())}..{float(totals.max())}")
                if not np.isfinite(shape.verts).all():
                    raise ValueError("Nonfinite fitted equipment geometry")
                for texture in shape.textures.values():
                    if not texture:
                        continue
                    file = (output / "mod" / texture.replace("\\", "/")).resolve()
                    if not file.is_relative_to(output / "mod") or not file.is_file():
                        raise ValueError(f"Fitted equipment texture is missing: {texture}")
                if shape.name.startswith("OriginalSkin_"):
                    normal_cosines.append(skin_normals(shape))
                    exposed += len(shape.tris)
                    maximum = max(maximum, float(tree.query(shape.verts)[0].max()))
                    if maximum > .001:
                        raise ValueError("Exposed skin is not the original VRM body")
                count += len(shape.tris)
        if observed_partitions != special_partitions:
            raise ValueError(f'Fitted headwear lost an original partition: {item["editor_id"]}: {observed_partitions} vs {special_partitions}')
        row = {"editor_id": item["editor_id"], "triangles": count,
               "original_exposed_skin_triangles": exposed, "original_skin_max_distance": maximum}
        cache[item['addon_local_id']] = row
        result.append(row)
    report = {"original_body_faces": len(triangles), "body_faces_preserved_exactly": True,
              "original_skin_min_normal_cosine": min(normal_cosines),
              "equipment": result, 'unique_equipment_meshes': len(cache), "game_verified": False}
    (output / "armor-validation.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    logging.info("Armor readback: %s original skin faces, %s fitted equipment", len(triangles), len(result))
    return report
