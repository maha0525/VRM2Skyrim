"""Export fitted equipment and unchanged, partitioned target skin in Blender."""
import argparse
import json
import logging
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dependencies"))
from settings import load_settings  # noqa: E402


def select(objects, active):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def submesh(source, faces, name, slot, rig):
    """Copy faces without moving vertices; preserve UVs, loop normals and skin."""
    mesh = source.data
    faces = [mesh.polygons[i] for i in faces]
    indices = sorted({i for face in faces for i in face.vertices})
    lookup = {old: new for new, old in enumerate(indices)}
    data = bpy.data.meshes.new(name)
    data.from_pydata([source.matrix_world @ mesh.vertices[i].co for i in indices], [],
                     [[lookup[i] for i in face.vertices] for face in faces])
    for mat in mesh.materials:
        data.materials.append(mat)
    loops = [i for face in faces for i in face.loop_indices]
    for old in mesh.uv_layers:
        uv = data.uv_layers.new(name=old.name)
        for new, index in enumerate(loops):
            uv.data[new].uv = old.data[index].uv
    for new, old in zip(data.polygons, faces):
        new.material_index = old.material_index
        new.use_smooth = old.use_smooth
    # Custom normals are encoded relative to the face's smoothing space.
    # Set smoothing first: changing it afterwards changes decoded normals.
    normals = [mesh.corner_normals[i].vector for i in loops]
    if normals:
        data.normals_split_custom_set(normals)
    for old in mesh.color_attributes:
        if old.domain not in ("POINT", "CORNER"):
            continue
        attr = data.color_attributes.new(name=old.name, type=old.data_type, domain=old.domain)
        for new, index in enumerate(indices if old.domain == "POINT" else loops):
            attr.data[new].color = old.data[index].color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    for key, value in source.items():
        obj[key] = value
    groups = {g.index: obj.vertex_groups.new(name=g.name) for g in source.vertex_groups if not g.name.startswith("SBP_")}
    for old, new in lookup.items():
        for group in mesh.vertices[old].groups:
            if group.group in groups:
                groups[group.group].add([new], group.weight, "REPLACE")
    obj.vertex_groups.new(name=f"SBP_{slot}_BODYADDON").add(list(range(len(indices))), 1., "REPLACE")
    obj.modifiers.new("Skyrim Skin", "ARMATURE").object = rig
    return obj


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    settings = load_settings(output)
    plan = json.loads((output / "armor-fit-plan.json").read_text())
    arrays = np.load(output / "armor-fit-arrays.npz")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="io_scene_nifly")
    skel = output / "mod/meshes" / settings.asset_dir / "skeleton.nif"
    bpy.ops.import_scene.pynifly(filepath=str(output / "armor-source/body.nif"), rename_bones=False,
                               create_bones=True, reference_skel=str(skel), import_animations=False,
                               import_shapekeys=False, import_collisions=False)
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    body = {obj.name: obj for obj in bpy.context.scene.objects if obj.type == "MESH"
            and any(m.type == "ARMATURE" for m in obj.modifiers)}
    from custom_skeleton import NifFile
    texture_map = {key.lower().replace("\\", "/"): value for key, value in plan["textures"].items()}

    def export(path, objects):
        if not objects:
            raise ValueError(f"No output geometry: {path}")
        select(objects + [rig], rig)
        bpy.ops.export_scene.pynifly(filepath=str(path), target_game="SKYRIMSE", rename_bones=False,
                                   blender_xf=False, preserve_hierarchy=True, export_modifiers=False,
                                   export_animations=False, export_colors=True, intuit_defaults=False)
        with NifFile(str(path)) as nif:
            for shape in nif.shapes:
                for slot, texture in shape.textures.items():
                    key = texture.lower().replace("\\", "/")
                    if key in texture_map:
                        shape.set_texture(slot, texture_map[key].replace("/", "\\"))
            nif.save()
        logging.info("Fitted NIF: %s (%s shapes)", path.name, len(objects))

    manifest = json.loads((output / "appearance.json").read_text())
    manifest["components"] = [part for part in manifest["components"] if part["role"] != "body"]
    region_sets = (("body", (32, 34, 38)), ("hands", (33,)), ("feet", (37,)))
    for region, slots in region_sets:
        objects = []
        for part in plan["body"]:
            source = body[part["name"]]
            for slot in slots:
                faces = [i for i, value in enumerate(part["face_slots"]) if value == slot]
                if faces:
                    objects.append(submesh(source, faces, f"{source.name}_{region}_{slot}", slot, rig))
        path = skel.parent / (region + ".nif")
        export(path, objects)
        manifest["components"].insert(0, {"id": region, "file": path.name, "role": "body",
                                           "nodes": settings.appearance_parts["body"], "slot": slots[0],
                                           "slots": list(slots), "partial_source": True,
                                           "nif": path.relative_to(output / "mod").as_posix()})
    for equipment in plan["equipment"]:
        existing = set(bpy.context.scene.objects)
        bpy.context.view_layer.objects.active = None
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.import_scene.pynifly(filepath=equipment["source"], rename_bones=False, create_bones=True,
                                   reference_skel=plan["source_skeleton"], import_animations=False,
                                   import_shapekeys=False, import_collisions=False)
        imported = [obj for obj in bpy.context.scene.objects if obj not in existing]
        meshes = {obj.name: obj for obj in imported if obj.type == "MESH"}
        objects = []
        for part in equipment["shapes"]:
            source = meshes[part["name"]]
            points = arrays[part["points"]]
            if len(source.data.vertices) != len(points):
                raise ValueError(f"Equipment import changed vertex order/count: {part['name']}")
            source.matrix_world = Matrix.Identity(4)
            source.parent = None
            source.data.vertices.foreach_set("co", points.ravel())
            source.data.normals_split_custom_set([(0., 0., 0.)] * len(source.data.loops))
            source.vertex_groups.clear()
            for name, pairs in part["weights"].items():
                group = source.vertex_groups.new(name=name)
                for index, value in pairs:
                    group.add([index], value, "REPLACE")
            for slot in sorted(set(part["face_slots"])):
                if slot not in equipment["slots"]:
                    raise ValueError("Armor shape partition is outside its addon")
                faces = [i for i, value in enumerate(part["face_slots"]) if value == slot]
                objects.append(submesh(source, faces, f"Fitted_{part['name']}_{slot}", slot, rig))
        for part in equipment["exposed_body"]:
            source = body[part["name"]]
            for slot in equipment["slots"]:
                faces = [i for i in part["faces"] if part["face_slots"][i] == slot]
                if faces:
                    objects.append(submesh(source, faces, f"OriginalSkin_{source.name}_{slot}", slot, rig))
        path = skel.parent / equipment["file"]
        export(path, objects)
        # Both engine weight variants are identical: retain one original VRM body.
        low = path.with_name(path.name.replace("_1.nif", "_0.nif"))
        low.write_bytes(path.read_bytes())
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
    (output / "appearance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    fitted = {"plugin": settings.plugin_name, "race_local_id": 0x804,
              "equipment": [{key: item[key] for key in ("editor_id", "original_form_id", "addon_local_id", "file", "slots", "priority")}
                            for item in plan["equipment"]]}
    path = output / "mod" / settings.asset_dir / "armor-fitting.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fitted, indent=2), encoding="utf8")
    (output / "armor-fitting.json").write_text(json.dumps(fitted, indent=2), encoding="utf8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "armor-fitted.blend"))


if __name__ == "__main__":
    main()
