"""VRM humanoid → proportion-preserving custom Skyrim skeleton and NIF."""
import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import sys

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dependencies"))
from inspect_vrm import humanoid_map, read_glb, write_glb  # noqa: E402
from settings import load_settings  # noqa: E402

LOG = logging.getLogger("converter")
CORE = {
    "hips": "NPC Pelvis [Pelv]", "spine": "NPC Spine [Spn0]",
    "chest": "NPC Spine2 [Spn2]", "upperChest": "NPC Spine2 [Spn2]",
    "neck": "NPC Neck [Neck]", "head": "NPC Head [Head]",
    "leftEye": "NPC Head [Head]", "rightEye": "NPC Head [Head]", "jaw": "NPC Head [Head]",
}
for side, letter in (("left", "L"), ("right", "R")):
    for vrm, skyrim, code in (
        ("Shoulder", "Clavicle", "Clv"), ("UpperArm", "UpperArm", "Uar"),
        ("LowerArm", "Forearm", "Lar"), ("Hand", "Hand", "Hnd"),
        ("UpperLeg", "Thigh", "Thg"), ("LowerLeg", "Calf", "Clf"),
        ("Foot", "Foot", "ft "), ("Toes", "Toe0", "Toe"),
    ):
        CORE[side + vrm] = f"NPC {letter} {skyrim} [{letter}{code}]"
    for finger, number in (("Thumb", 0), ("Index", 1), ("Middle", 2), ("Ring", 3), ("Little", 4)):
        parts = ("Metacarpal", "Proximal", "Distal") if finger == "Thumb" else ("Proximal", "Intermediate", "Distal")
        for joint, part in enumerate(parts):
            CORE[side + finger + part] = f"NPC {letter} Finger{number}{joint} [{letter}F{number}{joint}]"


def select_only(objects, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[0]


def save_images(meshes, output, settings, source_materials):
    png_dir = output / "texture-sources"
    png_dir.mkdir(parents=True, exist_ok=True)
    textures = []
    seen = {}
    materials = {slot.material for obj in meshes for slot in obj.material_slots if slot.material}
    for material in materials:
        info = source_materials[material.name]
        shader = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if shader is None:
            emission = next(node for node in material.node_tree.nodes if node.type == "EMISSION")
            shader = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            color = emission.inputs["Color"]
            shader.inputs["Base Color"].default_value = color.default_value
            if color.is_linked:
                material.node_tree.links.new(color.links[0].from_socket, shader.inputs["Base Color"])
            material.node_tree.links.new(shader.outputs["BSDF"], material.node_tree.nodes["Material Output"].inputs["Surface"])
        material["BS_Shader_Block_Name"] = "BSLightingShaderProperty"
        material.pyn_shader.Shader_Type = "Default"
        material.pyn_shader.Shader_Flags_1 = "SKINNED | RECEIVE_SHADOWS | CAST_SHADOWS | ZBUFFER_TEST"
        from nif_materials import lighting_flags_2
        material.pyn_shader.Shader_Flags_2 = lighting_flags_2(info)
        material.pyn_shader.Spec_Color = (0.0, 0.0, 0.0)
        material.pyn_shader.Alpha = (1. if info.get("alphaMode", "OPAQUE") == "OPAQUE" else
                                     info.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1, 1, 1, 1])[3])
        shader.inputs["Roughness"].default_value = 0.85
        shader.inputs["Specular IOR Level"].default_value = 0.1
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            image = node.image
            if image.name not in seen:
                stem = f"tex_{len(seen):03}_" + re.sub(r"[^a-z0-9_]", "_", image.name.lower())[:48]
                path = png_dir / (stem + ".png")
                image.filepath_raw = str(path)
                image.file_format = "PNG"
                image.save()
                # Exporter derives the DDS path from a 'textures' path component.
                relative = f"textures/{settings.asset_dir}/{stem}.dds"
                seen[image.name] = relative
                textures.append({"png": str(path), "relative": relative, "size": list(image.size)})
            image.filepath = str(output / "mod" / seen[image.name])
        material["BSShaderTextureSet_Normal"] = f"textures/{settings.asset_dir}/flat_n.dds"
    # Constant-color eye materials still require a texture in Skyrim's shader.
    for material in materials:
        shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        if not shader.inputs["Base Color"].is_linked:
            rgba = tuple(shader.inputs["Base Color"].default_value)
            image = bpy.data.images.new("solid_" + material.name, width=4, height=4)
            image.generated_color = rgba
            stem = re.sub(r"[^a-z0-9_]", "_", image.name.lower())
            path = png_dir / (stem + ".png")
            image.filepath_raw = str(path)
            image.file_format = "PNG"
            image.save()
            relative = f"textures/{settings.asset_dir}/{stem}.dds"
            image.filepath = str(output / "mod" / relative)
            node = material.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            material.node_tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
            textures.append({"png": str(path), "relative": relative, "size": [4, 4]})
    (output / "textures.json").write_text(json.dumps(textures, indent=2), encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skeleton", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    settings = load_settings(output)
    document, binary = read_glb(args.source)
    humanoid = humanoid_map(document)
    original_names = {index: node.get("name", "") for index, node in enumerate(document["nodes"])}
    from wardrobe import components, validate_source
    from inspect_vrm import inspect
    validate_source(settings, inspect(args.source))
    output_parts = components(settings, fitting=False)
    node_parts = {node: part for part in output_parts for node in (part["nodes"] or [])}
    node_parents = {child: index for index, node in enumerate(document["nodes"]) for child in node.get("children", [])}
    # Blender truncates/renames duplicate or long bone names; use deterministic
    # names on a temporary copy and keep the original file intact.
    for index, node in enumerate(document["nodes"]):
        node["name"] = f"VRMNode_{index:05}"
    for index, material in enumerate(document.get("materials", [])):
        material["name"] = f"VRMMaterial_{index:05}"
        legacy = document.get("extensions", {}).get("VRM", {}).get("materialProperties", [])
        if index < len(legacy):
            props = legacy[index].get("floatProperties", {})
            material.setdefault("extensions", {}).setdefault("VRMC_materials_mtoon", {})["transparentWithZWrite"] = props.get("_BlendMode") == 3
    source_materials = {item["name"]: item for item in document.get("materials", [])}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="io_scene_nifly")
    source_glb = output / "source.glb"
    write_glb(source_glb, document, binary)
    existing_objects = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(source_glb))
    imported_objects = [obj for obj in bpy.context.scene.objects if obj not in existing_objects]
    source_rigs = [obj for obj in imported_objects if obj.type == "ARMATURE"]
    hips_name = document["nodes"][humanoid["hips"]]["name"]
    source_rig = next((obj for obj in source_rigs if hips_name in obj.data.bones), None)
    if source_rig is None:
        raise ValueError("Humanoid hips are missing from the imported skin skeleton")
    meshes = [obj for obj in imported_objects if obj.type == "MESH"]
    custom_shapes = {bone.custom_shape for rig in source_rigs for bone in rig.pose.bones if bone.custom_shape}
    LOG.info("Imported meshes: %s", [(obj.name, obj.hide_render, obj in custom_shapes) for obj in meshes])
    meshes = [obj for obj in meshes if obj not in custom_shapes]
    for obj in meshes:
        node = int(obj.name.split("_")[-1].split(".")[0])
        obj["v2s_source_node"] = node
        obj["v2s_part"] = node_parts[node]["id"] if settings.armor_support else "appearance"
    default_material = bpy.data.materials.new("V2S_DefaultMaterial")
    default_material.use_nodes = True
    source_materials[default_material.name] = {}
    for obj in meshes:
        if not obj.material_slots:
            obj.data.materials.append(default_material)
        for slot in obj.material_slots:
            if slot.material is None:
                slot.material = default_material
    source_bones = {bone.name: bone for rig in source_rigs for bone in rig.data.bones}
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
        # Preserve any default morph weights before changing the armature pose.
        if obj.data.shape_keys:
            modifiers = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
            for mod in modifiers:
                mod.show_viewport = False
            bpy.context.view_layer.update()
            obj.data = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            for mod in modifiers:
                mod.show_viewport = True
            bpy.context.view_layer.update()
        if not any(mod.type == "ARMATURE" for mod in obj.modifiers):
            node_index = int(obj.name.split("_")[-1].split(".")[0])
            while node_index is not None and document["nodes"][node_index]["name"] not in source_bones:
                node_index = node_parents.get(node_index)
            name = document["nodes"][node_index]["name"] if node_index is not None else hips_name
            obj.vertex_groups.new(name=name).add(list(range(len(obj.data.vertices))), 1., "REPLACE")
            modifier = obj.modifiers.new("Rigid VRM attachment", "ARMATURE")
            modifier.object = next(rig for rig in source_rigs if name in rig.data.bones)
            LOG.info("Rigid attachment %s follows %s", obj.name, name)
    # Derive facing from the humanoid joints, not the model's version/name.
    # VRM 0 and 1 exporters can put the avatar in opposite forward directions.
    left_name = document["nodes"][humanoid["leftUpperArm"]]["name"]
    right_name = document["nodes"][humanoid["rightUpperArm"]]["name"]
    joint_world = {bone.name: rig.matrix_world @ bone.head_local for rig in source_rigs for bone in rig.data.bones}
    across = joint_world[left_name] - joint_world[right_name]
    if math.hypot(across.x, across.y) < 1e-7:
        raise ValueError("Cannot determine avatar facing from the shoulder joints")
    orient = Matrix.Rotation(math.pi - math.atan2(across.y, across.x), 4, "Z") @ Matrix.Scale(70.0, 4)
    source_positions = {bone.name: orient @ rig.matrix_world @ bone.head_local
                        for rig in source_rigs for bone in rig.data.bones}
    bone_names = {key: document["nodes"][index]["name"] for key, index in humanoid.items()}
    direct = {bone_names[key]: target for key, target in CORE.items() if key in bone_names}
    from parallel_rigs import follower_links, propagate_pose
    source_owners = {bone.name: rig.name for rig in source_rigs for bone in rig.data.bones}
    source_labels = {bone.name: original_names[int(bone.name.split("_")[-1])] for rig in source_rigs for bone in rig.data.bones}
    secondary_links, secondary_report = follower_links(source_positions, source_labels, source_owners,
                                                       {key: name for key, name in bone_names.items() if key in CORE})
    direct.update({secondary: direct[primary] for secondary, primary in secondary_links.items()})
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.import_scene.pynifly(filepath=str(args.skeleton), rename_bones=False, create_bones=False,
                               import_shapekeys=False, import_animations=False, import_collisions=False)
    target_rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and obj not in source_rigs)
    target_positions = {bone.name: target_rig.matrix_world @ bone.head_local for bone in target_rig.data.bones}
    for key in ("hips", "spine", "head", "leftUpperArm", "rightUpperArm", "leftLowerArm", "rightLowerArm",
                "leftHand", "rightHand", "leftUpperLeg", "rightUpperLeg", "leftLowerLeg", "rightLowerLeg", "leftFoot", "rightFoot"):
        if key not in bone_names or CORE[key] not in target_positions or bone_names[key] not in source_positions:
            raise ValueError(f"Missing required humanoid bone: {key}")
    mapping = {}
    for bone in source_bones.values():
        ancestor = bone
        while ancestor is not None and ancestor.name not in direct:
            ancestor = ancestor.parent
        mapping[bone.name] = direct[ancestor.name] if ancestor else CORE["hips"]

    from preserved_pose import preserved_transforms
    from custom_skeleton import create_skeleton, save_report

    source_parents = {bone.name: bone.parent.name if bone.parent else None
                      for bone in source_bones.values()}
    transforms, custom_positions, segment_stats = preserved_transforms(
        source_positions, bone_names, source_parents, target_positions, CORE)
    propagate_pose(transforms, source_parents, source_owners, secondary_links)
    physics_plan = {}
    physics_bones = {}
    physics_mesh_maps = {}
    if settings.physics_enabled:
        from physics_rig import plan_bones, selected_meshes, spring_nodes
        selected_nodes = selected_meshes(settings, original_names, [o['v2s_source_node'] for o in meshes])
        hints = spring_nodes(document)
        if not settings.physics_nodes:
            selected_nodes.update(o['v2s_source_node'] for o in meshes if any(
                o.vertex_groups[g.group].name in hints and g.weight > .001
                for v in o.data.vertices for g in v.groups))
        influences = {}
        mesh_components = {}
        fixed_bones = set()
        for obj in meshes:
            component = obj['v2s_part']
            if not settings.armor_support:
                component = ('appearance_hair' if 'hair' in original_names[obj['v2s_source_node']].lower()
                             else 'appearance_cloth')
            mesh_components[obj['v2s_source_node']] = component
            weights = (influences.setdefault(component, set())
                       if obj['v2s_source_node'] in selected_nodes else fixed_bones)
            for vertex in obj.data.vertices:
                weights.update(obj.vertex_groups[g.group].name for g in vertex.groups if g.weight > .001)
        for component, weighted in influences.items():
            # Split equipment can share source bones. Give each equipped
            # component its own copy rather than two physics systems writing
            # the same joint, or freezing a shared cloth chain.
            physics_plan = plan_bones(source_parents, direct, {component: weighted},
                                      settings.mod_id+'|'+component, hints, fixed_bones,
                                      {p['id'] for p in output_parts if p['role'] == 'garment'} | {'appearance_cloth'})
            for node in selected_nodes:
                if mesh_components[node] == component:
                    physics_mesh_maps[node] = {n: i['name'] for n, i in physics_plan.items()}
            for rig in source_rigs:
                for bone in rig.data.bones:
                    if bone.name not in physics_plan:
                        continue
                    info = physics_plan[bone.name]
                    value = np.asarray(Matrix(transforms[bone.name].tolist()) @ orient @ rig.matrix_world @ bone.matrix_local)
                    u, _, vt = np.linalg.svd(value[:3, :3])
                    rotation = u @ vt
                    if np.linalg.det(rotation) < 0:
                        raise ValueError(f'Reflected physics bone: {bone.name}')
                    value[:3, :3] = rotation
                    physics_bones[info['name']] = {**info, 'source': bone.name, 'label': source_labels[bone.name],
                                                 'matrix': value.tolist()}
        if not any(i['dynamic'] for i in physics_bones.values()):
            raise ValueError('選んだメッシュに揺らせる独立した骨がありません。髪・布のメッシュを選び直してください。')
        LOG.info('FSMP: preserving %s secondary bones, %s dynamic', len(physics_bones),
                 sum(i['dynamic'] for i in physics_bones.values()))
    custom_path = output / "mod/meshes" / settings.asset_dir / "skeleton.nif"
    skeleton_report = create_skeleton(args.skeleton, custom_path, custom_positions, physics_bones)
    save_report(skeleton_report, output)
    bpy.data.objects.remove(target_rig, do_unlink=True)
    bpy.context.view_layer.objects.active = None
    bpy.ops.import_scene.pynifly(filepath=str(custom_path), rename_bones=False, create_bones=False,
                               import_shapekeys=False, import_animations=False, import_collisions=False)
    target_rig = next(obj for obj in bpy.context.scene.objects
                      if obj.type == "ARMATURE" and obj not in source_rigs)

    # Independent baseline: let Blender pose the original VRM rig, then retain
    # evaluated vertices for comparison with the delivered NIF.
    for rig in source_rigs:
        source_world = rig.matrix_world.copy()
        for bone in rig.pose.bones:
            bone.matrix = (source_world.inverted() @ orient.inverted()
                           @ Matrix(transforms[bone.name].tolist()) @ orient
                           @ source_world @ bone.bone.matrix_local)
            bpy.context.view_layer.update()
        for bone in rig.pose.bones:
            requested = (source_world.inverted() @ orient.inverted()
                         @ Matrix(transforms[bone.name].tolist()) @ orient
                         @ source_world @ bone.bone.matrix_local)
            if np.max(np.abs(np.asarray(bone.matrix) - np.asarray(requested))) > 1e-5:
                raise ValueError(f"Original VRM pose baseline was not applied: {bone.name}")
    reference = bpy.data.collections.new("OriginalPoseReference")
    bpy.context.scene.collection.children.link(reference)
    expected = {}
    reference_materials = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated)
        mesh.transform(orient @ obj.matrix_world)
        # The source comparison retains its glTF alpha/unlit graph. Exporter
        # shader normalization owns only the delivered mesh's materials.
        for index, material in enumerate(mesh.materials):
            if material.name not in reference_materials:
                reference_materials[material.name] = material.copy()
                reference_materials[material.name].name = "Original_" + material.name
            mesh.materials[index] = reference_materials[material.name]
        copy = bpy.data.objects.new("Original_" + obj.name, mesh)
        reference.objects.link(copy)
        values = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", values)
        visible_vertices = sorted({index for polygon in mesh.polygons for index in polygon.vertices})
        expected[obj.name] = values.reshape((-1, 3))[visible_vertices]
    reference.hide_render = True
    reference.hide_viewport = True
    np.savez_compressed(output / "source-posed-vertices.npz", **expected)

    unweighted = {}
    for obj in meshes:
        LOG.info("Posing without stretch: %s (%s vertices)", obj.name, len(obj.data.vertices))
        mesh_mapping = {**mapping, **physics_mesh_maps.get(obj['v2s_source_node'], {})}
        vertices = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
        obj.data.vertices.foreach_get("co", vertices)
        vertices = vertices.reshape((-1, 3))
        common = np.asarray(orient @ obj.matrix_world)
        points = vertices @ common[:3, :3].T + common[:3, 3]
        weights = {}
        for vertex in obj.data.vertices:
            combined = {}
            for group in vertex.groups:
                name = obj.vertex_groups[group.group].name
                if name in mapping and group.weight > 1e-6:
                    combined[name] = combined.get(name, 0) + group.weight
            total = sum(combined.values())
            if not total:
                unweighted[obj.name] = unweighted.get(obj.name, 0) + 1
                continue
            for name, weight in combined.items():
                weights.setdefault(name, []).append((vertex.index, weight / total))
        if obj.name in unweighted:
            raise ValueError(f"Unweighted source vertices in {obj.name}: {unweighted[obj.name]}")
        fitted = np.zeros_like(points)
        target_weights = [{} for _ in points]
        for name, pairs in weights.items():
            indices = np.array([index for index, _ in pairs], dtype=int)
            values = np.array([weight for _, weight in pairs])
            matrix = np.asarray(transforms[name])
            fitted[indices] += (points[indices] @ matrix[:3, :3].T + matrix[:3, 3]) * values[:, None]
            target_name = mesh_mapping[name]
            for index, weight in pairs:
                target_weights[index][target_name] = target_weights[index].get(target_name, 0) + weight
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        obj.data.vertices.foreach_set("co", fitted.reshape(-1))
        if obj.data.has_custom_normals:
            obj.data.normals_split_custom_set([(0.0, 0.0, 0.0)] * len(obj.data.loops))
        for mod in list(obj.modifiers):
            obj.modifiers.remove(mod)
        obj.vertex_groups.clear()
        groups = {}
        for index, combined in enumerate(target_weights):
            limited = sorted(combined.items(), key=lambda item: item[1], reverse=True)[:4]
            total = sum(weight for _, weight in limited)
            for name, weight in limited:
                if name not in groups:
                    groups[name] = obj.vertex_groups.new(name=name)
                groups[name].add([index], weight / total, "REPLACE")
        slot = node_parts[obj["v2s_source_node"]]["slot"] if settings.armor_support else 32
        obj.vertex_groups.new(name=f"SBP_{slot}_" + ("BODY" if slot == 32 else "BODYADDON")).add(list(range(len(points))), 1.0, "REPLACE")
        armature = obj.modifiers.new("Skyrim Skin", "ARMATURE")
        armature.object = target_rig
        obj.data.update()
    for rig in source_rigs:
        bpy.data.objects.remove(rig, do_unlink=True)
    # PyNifly exports one shader per object; split each glTF primitive's material.
    for obj in list(bpy.context.scene.objects):
        if obj.type == "MESH" and len(obj.material_slots) > 1 and obj not in reference.objects.values():
            select_only([obj])
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="MATERIAL")
            bpy.ops.object.mode_set(mode="OBJECT")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"
              and any(mod.type == "ARMATURE" and mod.object == target_rig for mod in obj.modifiers)]
    from export_names import stabilize_mesh_names
    stabilize_mesh_names(meshes)
    from blender_meshes import partition_shape
    meshes = [part for obj in meshes for part in partition_shape(obj)]
    for obj in meshes:
        if len(obj.data.vertices) > 60000:
            raise ValueError(f"Mesh exceeds safe NIF shape vertex limit: {obj.name}")
    save_images(meshes, output, settings, source_materials)
    from nif_materials import apply_alpha
    manifest = []
    for part in output_parts:
        selected = [obj for obj in meshes if obj["v2s_part"] == part["id"]]
        if not selected:
            raise ValueError(f"Appearance component has no output geometry: {part['id']}")
        nif_path = output / "mod/meshes" / settings.asset_dir / part["file"]
        nif_path.parent.mkdir(parents=True, exist_ok=True)
        select_only(selected + [target_rig], target_rig)
        bpy.ops.export_scene.pynifly(filepath=str(nif_path), target_game="SKYRIMSE", rename_bones=False,
                                   blender_xf=False, preserve_hierarchy=True, export_modifiers=False,
                                   export_animations=False, export_colors=True, intuit_defaults=False)
        apply_alpha(nif_path, {obj.name: source_materials[obj.material_slots[0].material.name] for obj in selected})
        manifest.append({**part, "nif": nif_path.relative_to(output / "mod").as_posix(),
                         "shapes": [{"name": obj.name, "source_node": obj["v2s_source_node"],
                                     "double_sided": source_materials[obj.material_slots[0].material.name].get('doubleSided', False)} for obj in selected]})
        LOG.info("Exported component %s: %s shapes, slot %s", part["id"], len(selected), part["slot"])
    (output / "appearance.json").write_text(json.dumps({"components": manifest}, ensure_ascii=False, indent=2), encoding="utf8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "converted.blend"))
    if hashlib.sha256(args.source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("Source VRM changed during conversion")
    (output / "conversion.json").write_text(json.dumps({
        "source_sha256": source_hash, "bone_mapping": mapping, "preserved_segment_lengths": segment_stats,
        "source_node_names": original_names,
        "physics_mesh_mappings": physics_mesh_maps,
        "secondary_rigs": secondary_report, "secondary_bone_links": secondary_links,
        "pose_changes_are_rigid": True,
        "mesh_parts": [{"name": obj.name, "vertices": len(obj.data.vertices)} for obj in meshes],
        "unweighted_vertices": unweighted, "nifs": [part["nif"] for part in manifest],
    }, indent=2), encoding="utf-8")
    LOG.info("CONVERSION COMPLETE: %s", nif_path)


if __name__ == "__main__":
    main()
