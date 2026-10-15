"""Export fitted equipment and unchanged, partitioned target skin in Blender."""
import argparse
import json
import logging
from pathlib import Path
import sys
import re
from collections import defaultdict

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dependencies"))
from settings import load_settings  # noqa: E402
from armor_catalog import partition_slot  # noqa: E402


def select(objects, active):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def submesh(source, faces, name, slot, rig):
    """Copy faces without moving vertices; preserve UVs, loop normals and skin."""
    # The exporter strips Blender's .001 suffix, including a following slot.
    # Give each partition an explicit stable name so finishing edits round-trip.
    name = re.sub(r'\.(\d{3})', r'_copy\1', name)
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
    parser.add_argument('--mesh-key')
    parser.add_argument('--skin-only', action='store_true')
    parser.add_argument('--reuse-body', action='store_true')
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
    existing = set(bpy.context.scene.objects)
    bpy.context.view_layer.objects.active = None
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.import_scene.pynifly(filepath=str(skel), rename_bones=False, create_bones=False,
                               import_animations=False, import_shapekeys=False, import_collisions=False)
    full_rig = next(o for o in bpy.context.scene.objects if o not in existing and o.type == 'ARMATURE')
    for bone in rig.data.bones:
        if bone.name not in full_rig.data.bones or not np.allclose(np.asarray(rig.matrix_world@bone.matrix_local),
                    np.asarray(full_rig.matrix_world@full_rig.data.bones[bone.name].matrix_local), atol=.001):
            raise ValueError('Full attachment skeleton differs from the original body bind pose: '+bone.name)
    bpy.data.objects.remove(rig, do_unlink=True)
    rig = full_rig
    from custom_skeleton import NifFile
    texture_map = {key.lower().replace("\\", "/"): value for key, value in plan["textures"].items()}

    def export(path, objects, overrides=None):
        if not objects:
            raise ValueError(f"No output geometry: {path}")
        select(objects + [rig], rig)
        bpy.ops.export_scene.pynifly(filepath=str(path), target_game="SKYRIMSE", rename_bones=False,
                                   blender_xf=False, preserve_hierarchy=True, export_modifiers=False,
                                   export_animations=False, export_colors=True, intuit_defaults=False)
        with NifFile(str(path)) as nif:
            for shape in nif.shapes:
                for name, values in (overrides or {}).items():
                    if shape.name.startswith('Fitted_' + name + '_'):
                        for slot, texture in values.items():
                            shape.set_texture(slot, texture)
                for slot, texture in shape.textures.items():
                    key = texture.lower().replace("\\", "/")
                    if key in texture_map:
                        shape.set_texture(slot, texture_map[key].replace("/", "\\"))
                if shape.shader.blockname == 'BSEffectShaderProperty':
                    # This pinned DLL supports replacing an effect shader via
                    # addBlock; setBlock(type 33) is intentionally unimplemented.
                    shape.save_shader_attributes()
                    shape.write_properties()
            nif.save()
        logging.info("Fitted NIF: %s (%s shapes)", path.name, len(objects))

    manifest = json.loads((output / "appearance.json").read_text(encoding='utf8'))
    from appearance_materials import exported_shapes
    body_materials = {s['name']: s for part in manifest['components'] if part['role'] == 'body'
                      for s in part.get('shapes', [])}
    if not args.reuse_body:
        manifest["components"] = [part for part in manifest["components"] if part["role"] != "body"]
    region_sets = (("body", (32, 34, 38)), ("hands", (33,)), ("feet", (37,)))
    for region, slots in region_sets:
        if args.mesh_key or args.reuse_body:
            continue
        objects, bindings = [], {}
        for part in plan["body"]:
            source = body[part["name"]]
            for slot in slots:
                faces = [i for i, value in enumerate(part["face_slots"]) if value == slot]
                if faces:
                    obj = submesh(source, faces, f"{source.name}_{region}_{slot}", slot, rig)
                    objects.append(obj)
                    bindings[obj.name] = body_materials[part['name']]
        path = skel.parent / (region + ".nif")
        export(path, objects)
        manifest["components"].insert(0, {"id": region, "file": path.name, "role": "body",
                                           "nodes": settings.appearance_parts["body"], "slot": slots[0],
                                           "slots": list(slots), "partial_source": True,
                                           "shapes": exported_shapes(path, bindings),
                                           "nif": path.relative_to(output / "mod").as_posix()})
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for equipment in plan["equipment"]:
        if args.mesh_key and equipment['source_key'] != args.mesh_key:
            continue
        existing = set(bpy.context.scene.objects)
        bpy.context.view_layer.objects.active = None
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.import_scene.pynifly(filepath=equipment["source"], rename_bones=False, create_bones=True,
                                   reference_skel=plan["source_skeleton"], import_animations=False,
                                   import_shapekeys=False, import_collisions=False)
        imported = [obj for obj in bpy.context.scene.objects if obj not in existing]
        meshes = {obj.name: obj for obj in imported if obj.type == "MESH"}
        with NifFile(equipment['source']) as native:
            native_triangles = [shape.tris for shape in native.shapes]
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
            for material in source.data.materials:
                flags = material.pyn_shader.Shader_Flags_1
                if 'SKINNED' not in flags:
                    material.pyn_shader.Shader_Flags_1 = flags+' | SKINNED' if flags else 'SKINNED'
            source.vertex_groups.clear()
            for name, pairs in part["weights"].items():
                group = source.vertex_groups.new(name=name)
                for index, value in pairs:
                    group.add([index], value, "REPLACE")
            face_lookup = defaultdict(list)
            for triangle, slot in zip(native_triangles[part['index']], part['face_slots']):
                face_lookup[tuple(sorted(triangle))].append(slot)
            face_slots = []
            for polygon in source.data.polygons:
                key = tuple(sorted(polygon.vertices))
                if not face_lookup[key]:
                    raise ValueError(f'Equipment importer changed triangle topology: {part["name"]}')
                face_slots.append(face_lookup[key].pop(0))
            dropped = sum(len(values) for values in face_lookup.values())
            if dropped:
                logging.info('Blender omitted %s degenerate/duplicate source faces: %s', dropped, part['name'])
            for slot in sorted(set(face_slots)):
                layer = partition_slot(slot, equipment['slots'][0])
                if layer not in equipment["slots"]:
                    raise ValueError("Armor shape partition is outside its addon")
                faces = [i for i, value in enumerate(face_slots) if value == slot]
                objects.append(submesh(source, faces, f"Fitted_{part['name']}_{layer}", slot, rig))
        for part in equipment["exposed_body"]:
            source = body[part["name"]]
            for slot in equipment["slots"]:
                faces = [i for i in part["faces"] if part["face_slots"][i] == slot]
                if faces:
                    objects.append(submesh(source, faces, f"OriginalSkin_{source.name}_{slot}", slot, rig))
        path = skel.parent / equipment["file"]
        from outfit_edits import apply_to_blender
        apply_to_blender(objects, settings.appearance_source_sha256, equipment['source_key'])
        export(path, objects, equipment.get('texture_overrides'))
        # Both engine weight variants are identical: retain one original VRM body.
        low = path.with_name(path.name.replace("_1.nif", "_0.nif"))
        low.write_bytes(path.read_bytes())
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.orphans_purge(do_recursive=True)
    if not args.mesh_key:
        (output / "appearance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    if args.skin_only:
        return
    geometries = {item['mesh_index']: item for item in plan['equipment']}
    fitted = {"plugin": settings.plugin_name, "race_local_id": 0x804, 'schema': 2,
              'wardrobe_policy': settings.wardrobe_policy,
              'source_profile': plan['source_profile'], 'reference_signature': plan.get('reference_signature'), 'plugins': plan['plugins'],
              'avatar_sha256': settings.appearance_source_sha256,
              'equipment': [{**binding, **{key: geometries[binding['mesh_index']][key] for key in
                                         ('addon_local_id', 'file', 'slots', 'priority', 'source_key')}}
                            for binding in plan['bindings']]}
    path = output / "mod" / settings.asset_dir / "armor-fitting.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fitted, indent=2), encoding="utf8")
    (output / "armor-fitting.json").write_text(json.dumps(fitted, indent=2), encoding="utf8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "armor-fitted.blend"))


if __name__ == "__main__":
    main()
