"""Render only the exported NIF, with actual vanilla HKX animation when requested."""
import argparse
import json
import logging
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies"))
sys.path.insert(0, str(ROOT))
from settings import load_settings, reference_root  # noqa: E402


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--animation", choices=("original", "rest", "walk", "attack"), default="rest")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    settings = load_settings(output)
    refs = reference_root(output)
    previews = output / "previews"
    previews.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="io_scene_nifly")
    skel = output / "mod/meshes" / settings.asset_dir / "skeleton.nif"
    nif = output / "mod/meshes" / settings.asset_dir / "avatar.nif"
    bpy.ops.import_scene.pynifly(filepath=str(nif), rename_bones=False, create_bones=True,
                               reference_skel=str(skel), import_animations=False,
                               import_shapekeys=False, import_collisions=False)
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"
              and any(mod.type == "ARMATURE" and mod.object == rig for mod in obj.modifiers)]
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
    scene.camera = camera
    for location, power, size in [((1.8, 2.8, 3.5), 80, 3), ((-2, 1.5, 2), 45, 2), ((0, -2, 3), 60, 2)]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = power
        light.data.shape = "DISK"
        light.data.size = size
        aim(light, (0, 0, 0.8))
    for frame in frames:
        scene.frame_set(frame)
        if weapon is not None:
            hand = rig.pose.bones["NPC R Hand [RHnd]"]
            # The mesh importer omits unweighted attachment bones. Recover the
            # actual attachment from the delivered skeleton, then pose its hand.
            weapon.matrix_world = (rig.matrix_world @ hand.matrix
                                   @ hand.bone.matrix_local.inverted() @ weapon_rest)
            bpy.context.view_layer.update()
        scene.render.filepath = str(previews / f"{args.animation}-{frame:02}.png")
        bpy.ops.render.render(write_still=True)
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
        scene.render.filepath = str(previews / "attack-hand-10.png")
        bpy.ops.render.render(write_still=True)
    (previews / f"{args.animation}.json").write_text(json.dumps({
        "nif": str(nif), "animation": args.animation, "frames": frames,
        "meshes": [obj.name for obj in meshes], "game_verified": False,
        "steel_sword_geometry": weapon is not None,
        "weapon_attachment": "WEAPON" if weapon else None,
        "weapon_material": "neutral metal preview" if weapon else None,
    }, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"preview-{args.animation}.blend"))


if __name__ == "__main__":
    main()
