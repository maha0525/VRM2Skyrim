"""Render classified source meshes in an isolated, factory-startup Blender."""
import argparse
import json
import logging
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from inspect_vrm import inspect, read_glb, write_glb  # noqa: E402
from settings import load_settings  # noqa: E402
from wardrobe import validate_source, original_head_visibility  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wardrobe", default="all")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    settings = load_settings(output)
    validate_source(settings, inspect(args.source))
    parts = settings.appearance_parts
    selected = set(parts["body"] + parts["underwear"] + parts["fixed"])
    if args.wardrobe not in ("all", "underwear") and args.wardrobe not in {"without:" + g["id"] for g in parts["garments"]}:
        raise ValueError("Unknown preview wardrobe state")
    visible_garments = []
    for garment in parts["garments"]:
        if args.wardrobe != "underwear" and args.wardrobe != "without:" + garment["id"]:
            selected.update(garment["nodes"])
            visible_garments.append(garment)
    policy = original_head_visibility(visible_garments)
    for part in ('face', 'hair'):
        if policy['hide_' + part]:
            selected.difference_update(settings.appearance_heads.get(part, []))
    document, binary = read_glb(args.source)
    from nif_materials import normalize_material_colors
    normalize_material_colors(document)
    for index, node in enumerate(document["nodes"]):
        node["name"] = f"VRMNode_{index:05}"
    for index, material in enumerate(document.get('materials', [])):
        material['name'] = f'VRMMaterial_{index:05}'
    source_materials = {m['name']: m for m in document.get('materials', [])}
    glb = output / "preview-source.glb"
    write_glb(glb, document, binary)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    helpers = {bone.custom_shape for rig in rigs for bone in rig.pose.bones if bone.custom_shape}
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj not in helpers]
    from blender_meshes import preview_face_culling
    for material in bpy.data.materials:
        info = source_materials.get(material.name, {})
        material['V2S_Preview_Policy'] = json.dumps(info)
        preview_face_culling(material, info.get('doubleSided', False))
    if settings.toon_enabled:
        from toon_preview import apply_toon_preview
        apply_toon_preview(output, meshes, source_glb=glb, units_per_metre=1.0)
    bounds = []
    for obj in meshes:
        node = int(obj.name.split("_")[-1].split(".")[0])
        obj.hide_render = node not in selected
        bounds.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    lo = Vector(tuple(min(p[i] for p in bounds) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in bounds) for i in range(3)))
    center, height = (lo + hi) / 2, max(hi.z - lo.z, .2)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 600, 800
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("Classification World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.14, .15, .17, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .5
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(height * 1.25, (hi.x - lo.x) * 800 / 600 * 1.1)
    scene.camera = camera
    for offset, energy, size in [((1,-2,2),100,2),((-1,-1,1),40,2),((0,1,2),90,2)]:
        bpy.ops.object.light_add(type="AREA", location=center + Vector(offset) * height)
        light = bpy.context.object
        light.data.energy, light.data.size = energy, size * height
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    # Either direction may be the front depending on the VRM exporter.
    for side, sign in (("front", -1), ("back", 1)):
        camera.location = center + Vector((0, sign * height * 3, height * .05))
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(output / (side + ".png"))
        from blender_meshes import render_material_queues
        render_material_queues(scene)
    (output / "preview.json").write_text(json.dumps({"source_nodes": sorted(selected), "wardrobe": args.wardrobe,
                                                    "kind": "source_classification", "game_verified": False}), encoding="utf8")


if __name__ == "__main__":
    main()
