"""Render only the exported NIF, with actual vanilla HKX animation when requested."""
import argparse
import json
import logging
from pathlib import Path
import sys
import numpy as np

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies"))
sys.path.insert(0, str(ROOT))
from settings import load_settings, reference_root  # noqa: E402
from armor_catalog import partition_slot  # noqa: E402


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--animation", choices=("original", "rest", "walk", "attack"), default="rest")
    parser.add_argument("--wardrobe", default="initial", help="initial, all, underwear, without:<garment-id>")
    parser.add_argument('--hide-face', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--hide-hair', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--keep-clothes', action='store_true')
    parser.add_argument('--head-closeup', action='store_true')
    parser.add_argument('--physics-frame', type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    settings = load_settings(output)
    refs = reference_root(output)
    previews = output / "previews"
    previews.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="io_scene_nifly")
    skel = output / "mod/meshes" / settings.asset_dir / "skeleton.nif"
    from wardrobe import components, original_head_visibility
    parts = components(settings)
    manifest = json.loads((output/'appearance.json').read_text(encoding='utf8'))['components']
    for part in parts:
        original = next((p for p in manifest if p['id'] == part['id']), None)
        if original:
            # Fitting regenerates split skin components without per-source
            # shape metadata. Their materials are imported from the NIF itself.
            part['shapes'] = original.get('shapes', []) if original.get('partial_source') else original['shapes']
    wardrobe = args.wardrobe
    if wardrobe.startswith("armor:"):
        fitting = json.loads((output / "armor-fitting.json").read_text(encoding='utf8'))
        chosen = wardrobe[6:]
        unknown = set(chosen.split(',')) - {p['editor_id'] for p in fitting['equipment']}
        if chosen != 'all' and unknown:
            raise ValueError(f"Unknown fitted armor: {', '.join(sorted(unknown))}")
        selected = [p for p in fitting["equipment"] if chosen == "all" or p["editor_id"] in chosen.split(',')]
        if not selected:
            raise ValueError("Unknown fitted armor")
        if chosen == "all":
            # Conversion can include many alternatives at the same equip slot.
            # Show one compatible representative per primary slot, as the game
            # cannot wear two cuirasses (or two pairs of boots) simultaneously.
            compatible, occupied = [], set()
            for item in selected:
                slots = set(item['slots'])
                if not occupied.intersection(slots):
                    compatible.append(item)
                    occupied.update(slots)
            selected = compatible
        if args.hide_face if args.hide_face is not None else any(p.get('hide_face') for p in selected):
            parts = [p for p in parts if p['id'] != 'face']
        if args.hide_hair if args.hide_hair is not None else any(p.get('hide_hair') for p in selected):
            parts = [p for p in parts if p['id'] != 'hair']
        parts += [{**p, "role": "equipment", "slot": p["slots"][0]} for p in selected]
    elif wardrobe not in ("initial", "all", "underwear") and not any(wardrobe == "without:" + p["id"] for p in parts if p["role"] == "garment"):
        raise ValueError("Unknown wardrobe state")
    if settings.armor_support:
        parts = [p for p in parts if p['role'] != 'garment' or not (
            (wardrobe.startswith('armor:') and not args.keep_clothes) or wardrobe == 'underwear' or wardrobe == 'without:'+p['id'] or
            (wardrobe == 'initial' and not p['equipped']))]
        policy = original_head_visibility([p for p in parts if p['role'] == 'garment'])
        for name in ('face', 'hair'):
            if policy['hide_' + name]:
                parts = [p for p in parts if p['id'] != name]
    slot_priority = {}
    for part in parts:
        for slot in part.get("slots", [part["slot"]]):
            slot_priority[slot] = max(slot_priority.get(slot, 0), part.get("priority", 0))
    nifs, rig = [], None
    if settings.skin_partition_enabled:
        # Use the complete original skin's import as the common preview rig.
        # Importers orient unweighted helper bones differently after partitioning.
        bpy.ops.import_scene.pynifly(filepath=str(output / "armor-source/body.nif"), rename_bones=False,
                                   create_bones=True, reference_skel=str(skel), import_animations=False,
                                   import_shapekeys=False, import_collisions=False)
        rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
        for obj in list(bpy.context.scene.objects):
            if obj.type == "MESH":
                bpy.data.objects.remove(obj, do_unlink=True)
        existing = set(bpy.context.scene.objects)
        bpy.context.view_layer.objects.active = None
        bpy.ops.import_scene.pynifly(filepath=str(skel), rename_bones=False, create_bones=False,
                                   import_animations=False, import_shapekeys=False, import_collisions=False)
        full = next(o for o in bpy.context.scene.objects if o not in existing and o.type == 'ARMATURE')
        for bone in rig.data.bones:
            if not np.allclose(np.asarray(rig.matrix_world@bone.matrix_local),
                               np.asarray(full.matrix_world@full.data.bones[bone.name].matrix_local), atol=.001):
                raise ValueError('Attachment skeleton changes the original body bind pose')
        bpy.data.objects.remove(rig, do_unlink=True)
        rig = full
    for part in parts:
        if settings.armor_support and part["role"] == "garment":
            if (wardrobe.startswith("armor:") and not args.keep_clothes) or wardrobe == "underwear" or wardrobe == "without:" + part["id"] or (wardrobe == "initial" and not part["equipped"]):
                continue
        nif = output / "mod/meshes" / settings.asset_dir / part["file"]
        nifs.append(str(nif))
        existing = set(bpy.context.scene.objects)
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = None
        bpy.ops.import_scene.pynifly(filepath=str(nif), rename_bones=False, create_bones=True,
                                   reference_skel=str(skel), import_animations=False,
                                   import_shapekeys=False, import_collisions=False)
        imported = [obj for obj in bpy.context.scene.objects if obj not in existing]
        for obj in imported:
            if obj.type == 'MESH':
                policy = next((p.get('material_policy') for p in part.get('shapes', []) if p['name'] == obj.name), None)
                if policy is not None:
                    for material in obj.data.materials:
                        if material:
                            material['V2S_Preview_Policy'] = json.dumps(policy)
        for obj in imported:
            if obj.type == 'MESH' and obj.name.startswith('V2SCollision_'):
                obj.hide_render = True
        if settings.armor_support:
            import re
            for obj in imported:
                if obj.type != "MESH":
                    continue
                slots = {partition_slot(int(m.group(1)), part['slot']) if int(m.group(1)) >= 100 else int(m.group(1)) for g in obj.vertex_groups
                         if (m := re.match(r"SBP_(\d+)_", g.name))}
                if slots and all(slot_priority.get(s, 0) > part.get("priority", 0) for s in slots):
                    obj.hide_render = True
        new_rig = next(obj for obj in imported if obj.type == "ARMATURE")
        if rig is None:
            rig = new_rig
        else:
            weighted = {group.name for obj in imported if obj.type == "MESH" for group in obj.vertex_groups
                        if not group.name.startswith("SBP_")}
            for bone in new_rig.data.bones:
                if settings.skin_partition_enabled and bone.name not in weighted:
                    continue
                if bone.name not in rig.data.bones or not np.allclose(np.array(bone.matrix_local), np.array(rig.data.bones[bone.name].matrix_local), atol=.001):
                    raise ValueError(f"Separated appearance uses inconsistent bone rest pose: {bone.name}")
            for obj in imported:
                world = obj.matrix_world.copy()
                if obj.parent == new_rig:
                    obj.parent = rig
                    obj.matrix_world = world
                for modifier in obj.modifiers:
                    if modifier.type == "ARMATURE" and modifier.object == new_rig:
                        modifier.object = rig
            bpy.data.objects.remove(new_rig, do_unlink=True)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.hide_render
              and any(mod.type == "ARMATURE" and mod.object == rig for mod in obj.modifiers)]
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj not in meshes:
            obj.hide_render = True  # Skeleton bounds/custom-shape helpers are editor metadata.
    from blender_meshes import preview_face_culling
    for material in {m for obj in meshes for m in obj.data.materials if m}:
        preview_face_culling(material, 'DOUBLE_SIDED' in material.pyn_shader.Shader_Flags_2)
    # These PNGs were decoded from the delivered DDS, not copied from the VRM.
    for image in bpy.data.images:
        if image.filepath:
            image.filepath = str(output / "dds-preview" / (Path(image.filepath).stem + ".png"))
            image.reload()
    frames = [1]
    if args.animation == "original":
        for obj in meshes:
            obj.hide_render = True
        with bpy.data.libraries.load(str(output / "converted.blend"), link=False) as (source, target):
            target.collections = ["OriginalPoseReference"]
        collection = target.collections[0]
        scene = bpy.context.scene
        scene.collection.children.link(collection)
        collection.hide_render = False
        collection.hide_viewport = False
        for image in bpy.data.images:
            if image.filepath:
                path = output / "dds-preview" / (Path(image.filepath).stem + ".png")
                if path.exists():
                    image.filepath = str(path)
                    image.reload()
    elif args.animation != "rest":
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        base = refs / "meshes/actors/character"
        animation = base / (f"animations/{settings.sex}/mt_walkforward.hkx" if args.animation == "walk"
                            else "animations/1hm_attackright.hkx")
        bpy.ops.import_scene.pynifly_hkx(filepath=str(animation), rename_bones=False,
                                       reference_skel=str(base / "character assets/skeleton.hkx"))
        frames = [1, 8, 16, 24] if args.animation == "walk" else [1, 5, 10, 16]
    weapon = None
    if args.animation == "attack":
        from custom_skeleton import NifFile, matrix
        with NifFile(str(skel)) as skeleton_file:
            weapon_rest = Matrix(matrix(skeleton_file.nodes["WEAPON"].global_transform).tolist())
        existing = set(bpy.context.scene.objects)
        bpy.context.view_layer.objects.active = None
        bpy.ops.import_scene.pynifly(
            filepath=str(refs / "meshes/weapons/steel/steelsword.nif"),
            rename_bones=False, import_animations=False, import_collisions=False)
        sword_parts = [obj for obj in bpy.context.scene.objects if obj not in existing]
        weapon = bpy.data.objects.new("Steel sword attachment", None)
        bpy.context.scene.collection.objects.link(weapon)
        metal = bpy.data.materials.new("Sword preview metal")
        metal.use_nodes = True
        shader = metal.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (0.2, 0.22, 0.24, 1)
        shader.inputs["Metallic"].default_value = 0.7
        shader.inputs["Roughness"].default_value = 0.3
        for obj in sword_parts:
            if obj.type == "MESH":
                obj.hide_render = not obj.name.startswith("SteelSword")
                obj.data.materials.clear()
                obj.data.materials.append(metal)
            if obj.parent is None:
                obj.parent = weapon
    # Scale the whole hierarchy for lighting; keep imported bone bind transforms.
    physics_sample = None
    if args.physics_frame is not None:
        sample = json.loads((output/'physics-preview.json').read_text(encoding='utf8'))['frames'][str(args.physics_frame)]
        physics_sample = sample
        logging.info('Physics preview rig %s: %s matched bones; deform flags %s', rig.name,
                     len(set(sample) & set(rig.pose.bones.keys())),
                     [(b.name, b.use_deform) for b in rig.data.bones if b.name in sample][:4])
    roots = [obj for obj in bpy.context.scene.objects if obj.parent is None]
    parent = bpy.data.objects.new("Preview Units", None)
    bpy.context.scene.collection.objects.link(parent)
    for obj in roots:
        obj.parent = parent
    parent.scale = (0.01,) * 3
    bpy.context.view_layer.update()
    bounds = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[axis] for point in bounds) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in bounds) for axis in range(3)))
    center = (minimum + maximum) / 2
    height = max(maximum.z - minimum.z, .2)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 720
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("Preview World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.12, 0.14, 0.18, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3
    bpy.ops.object.camera_add(location=center + Vector((height * 1.8, height * 4, height * .55)))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(height * 1.45, (maximum.x - minimum.x) * 1.45 * 900 / 720)
    aim(camera, center)
    if args.head_closeup:
        head = rig.matrix_world @ rig.data.bones['NPC Head [Head]'].head_local
        # Frame the head and shoulders, including fitted helmets and long ears.
        head_center = head + Vector((0, 0, height * .035))
        camera.location = head_center + Vector((height * .7, height * 2, height * .1))
        camera.data.ortho_scale = height * .42
        aim(camera, head_center)
    scene.camera = camera
    for location, power, size in [((1.8, 2.8, 3.5), 80, 3), ((-2, 1.5, 2), 45, 2), ((0, -2, 3), 60, 2)]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = power
        light.data.shape = "DISK"
        light.data.size = size
        aim(light, (0, 0, 0.8))
    prefix = args.animation if wardrobe == "initial" else "wardrobe-" + wardrobe.replace(":", "-") + "-" + args.animation
    if args.physics_frame is not None:
        prefix = 'physics-'+str(args.physics_frame)
    for frame in frames:
        scene.frame_set(frame)
        if physics_sample is not None:
            for bone in rig.pose.bones:
                if bone.name in physics_sample:
                    # Physics matrices are in unscaled game space; preview
                    # hierarchy scaling is a lighting-only transform.
                    bone.matrix = Matrix(physics_sample[bone.name]) @ bone.bone.matrix_local
                    bpy.context.view_layer.update()
        if weapon is not None:
            hand = rig.pose.bones["NPC R Hand [RHnd]"]
            # The mesh importer omits unweighted attachment bones. Recover the
            # actual attachment from the delivered skeleton, then pose its hand.
            weapon.matrix_world = (rig.matrix_world @ hand.matrix
                                   @ hand.bone.matrix_local.inverted() @ weapon_rest)
            bpy.context.view_layer.update()
        scene.render.filepath = str(previews / f"{prefix}-{frame:02}.png")
        from blender_meshes import render_material_queues
        render_material_queues(scene)
    if weapon is not None:
        scene.frame_set(10)
        hand = rig.pose.bones["NPC R Hand [RHnd]"]
        weapon.matrix_world = (rig.matrix_world @ hand.matrix
                               @ hand.bone.matrix_local.inverted() @ weapon_rest)
        bpy.context.view_layer.update()
        center = rig.matrix_world @ hand.head
        camera.location = center + Vector((.5, 1.0, .35))
        camera.data.ortho_scale = .32
        aim(camera, center)
        scene.render.filepath = str(previews / ("attack-hand-10.png" if wardrobe == "initial" else prefix + "-hand-10.png"))
        render_material_queues(scene)
    (previews / f"{prefix}.json").write_text(json.dumps({
        "nifs": nifs, "animation": args.animation, "frames": frames, "wardrobe": wardrobe,
        "meshes": [obj.name for obj in meshes], "game_verified": False,
        "steel_sword_geometry": weapon is not None,
        "weapon_attachment": "WEAPON" if weapon else None,
        "weapon_material": "neutral metal preview" if weapon else None,
    }, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"preview-{prefix}.blend"))


if __name__ == "__main__":
    main()
