"""Original weapon beside its base official weapon at the same scale; the grip (NIF origin) is marked."""
import argparse
import json
import logging
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies"))
sys.path.insert(0, str(ROOT))
from render_blender import aim, frame_camera, import_original_weapon  # noqa: E402


def material(name, color, emission=0.):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = .45
    if emission:
        shader.inputs["Emission Color"].default_value = color
        shader.inputs["Emission Strength"].default_value = emission
    return result


def import_base(nif):
    """Official weapon geometry without scabbard and blood shapes, in a neutral material."""
    existing = set(bpy.context.scene.objects)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.import_scene.pynifly(filepath=str(nif), rename_bones=False, import_animations=False,
                                 import_collisions=False)
    imported = [obj for obj in bpy.context.scene.objects if obj not in existing]
    for obj in [o for o in imported if o.type not in ("MESH", "EMPTY")]:
        imported.remove(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
    grey = material("Base weapon", (.32, .34, .37, 1))
    shown = []
    for obj in imported:
        if obj.type == "MESH":
            name = obj.name.lower()
            obj.hide_render = name.startswith("scb") or "blood" in name
            obj.data.materials.clear()
            obj.data.materials.append(grey)
            if not obj.hide_render:
                shown.append(obj)
    if not shown:
        raise ValueError(f"Base weapon NIF has no weapon shapes: {nif}")
    root = bpy.data.objects.new("Base weapon", None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            obj.parent = root
    return root, shown


def local_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return (Vector(tuple(min(p[i] for p in points) for i in range(3))),
            Vector(tuple(max(p[i] for p in points) for i in range(3))))


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--weapon-nif", type=Path, required=True)
    parser.add_argument("--weapon-textures", type=Path, required=True)
    parser.add_argument("--base-nif", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    for name in ("weapon_nif", "weapon_textures", "base_nif", "output"):
        setattr(args, name, getattr(args, name).resolve())  # Blender resolves relative paths elsewhere
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="io_scene_nifly")
    weapon, weapon_meshes = import_original_weapon(args.weapon_nif, args.weapon_textures)
    base, base_meshes = import_base(args.base_nif)
    bpy.context.view_layer.update()
    # NIF units: +Y is the weapon's length and the origin is the grip.
    weapon_low, weapon_high = local_bounds(weapon_meshes)
    base_low, base_high = local_bounds(base_meshes)
    length = max(weapon_high.y - weapon_low.y, base_high.y - base_low.y)
    base.location.x = weapon_high.x - base_low.x + .3 * length
    bpy.context.view_layer.update()
    base_low, base_high = local_bounds(base_meshes)
    front = max(weapon_high.z, base_high.z) + 1
    marker = bpy.data.meshes.new("Grip marker")
    left, right = weapon_low.x - .12 * length, base_high.x + .12 * length
    width = .006 * length
    marker.from_pydata([(left, -width, front), (right, -width, front), (right, width, front), (left, width, front)],
                       [], [(0, 1, 2, 3)])
    grip = bpy.data.objects.new("Grip marker", marker)
    bpy.context.scene.collection.objects.link(grip)
    grip.data.materials.append(material("Grip marker", (.95, .2, .15, 1), 2.))
    # Stand the weapons up (NIF +Y -> world +Z) in preview units like render_blender.py.
    pivot = bpy.data.objects.new("Preview Units", None)
    bpy.context.scene.collection.objects.link(pivot)
    for obj in (weapon, base, grip):
        obj.parent = pivot
    pivot.matrix_world = Matrix.Rotation(math.radians(90), 4, "X") @ Matrix.Scale(.01, 4)
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 720, 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("Preview World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.12, 0.14, 0.18, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    frame_camera(camera, weapon_meshes + base_meshes + [grip], (0, -1, 0), 1.08)
    center = sum((obj.matrix_world.translation for obj in (weapon, base)), Vector()) / 2
    for offset, power in (((1.5, -3, 2), 120), ((-2, -2, .5), 60), ((0, 2.5, 1.5), 60)):
        bpy.ops.object.light_add(type="AREA", location=center + Vector(offset))
        light = bpy.context.object
        light.data.energy, light.data.size = power, 2
        aim(light, center)
    scene.render.filepath = str(args.output)
    bpy.ops.render.render(write_still=True)
    args.output.with_suffix(".json").write_text(json.dumps({
        "weapon_nif": str(args.weapon_nif), "base_nif": str(args.base_nif), "grip_marker": "NIF origin (y = 0)",
        "weapon_y": [weapon_low.y, weapon_high.y], "base_y": [base_low.y, base_high.y], "game_verified": False},
        indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
