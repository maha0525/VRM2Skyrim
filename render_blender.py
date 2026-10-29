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


def import_original_weapon(nif, textures):
    """Import the original weapon NIF with the PNGs decoded from its delivered DDS."""
    from blender_meshes import preview_face_culling
    existing = set(bpy.context.scene.objects)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.import_scene.pynifly(filepath=str(nif), rename_bones=False, import_animations=False,
                                 import_collisions=False)
    imported = [obj for obj in bpy.context.scene.objects if obj not in existing]
    for obj in [o for o in imported if o.type not in ("MESH", "EMPTY")]:
        imported.remove(obj)  # BSInvMarker imports as an inventory camera
        bpy.data.objects.remove(obj, do_unlink=True)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise ValueError(f"Original weapon NIF has no shapes: {nif}")
    attachment = bpy.data.objects.new("Original weapon attachment", None)
    bpy.context.scene.collection.objects.link(attachment)
    for obj in imported:
        if obj.parent is None:
            obj.parent = attachment
    for obj in meshes:
        material = obj.active_material
        images = [n for n in material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image] if material else []
        if not any(n.name == "Diffuse_Texture" for n in images):
            raise ValueError(f"Original weapon shape imported without its diffuse texture: {obj.name}")
        preview_face_culling(material, 'DOUBLE_SIDED' in material.pyn_shader.Shader_Flags_2)
        for node in images:
            png = Path(textures) / (Path(node.image.filepath).stem + ".png")
            if not png.is_file():
                raise FileNotFoundError(f"Decoded original weapon texture is missing: {png}")
            node.image.filepath = str(png)
            node.image.reload()
    return attachment, meshes


def global_matrix(node):
    from custom_skeleton import matrix
    return Matrix(matrix(node.global_transform).tolist())


def unscaled(m):
    return Matrix.LocRotScale(m.translation, m.to_quaternion(), None)


def attachment_node(skeleton_file, name):
    node = skeleton_file.nodes[name]
    return name, node.parent.name, global_matrix(node), global_matrix(node.parent)


def add_attachment_bones(rig, skeleton_file, names):
    """Add the skeleton's attachment nodes the mesh importer omits (they carry no weights),
    so the animation import poses them."""
    missing = [n for n in names if n in skeleton_file.nodes and n not in rig.data.bones]
    if not missing:
        return
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for name in missing:
        node = skeleton_file.nodes[name]
        parent = rig.data.edit_bones[node.parent.name]
        # The parent bone's offset from its node carries the importer's bone-axis convention.
        convention = unscaled(global_matrix(node.parent)).inverted() @ parent.matrix
        bone = rig.data.edit_bones.new(name)
        bone.tail = (0, 5, 0)
        bone.matrix = unscaled(global_matrix(node)) @ convention
        bone.parent, bone.use_deform = parent, False
    bpy.ops.object.mode_set(mode='OBJECT')


def attach(weapon, rig, node):
    """Place a weapon on a skeleton node: its parent's posed bone, then the node's local
    transform, animated when the animation has a track for the node itself (vanilla HKX
    animate WEAPON; staffright_idle rolls it ~180° about the weapon's length)."""
    name, parent_name, rest, parent_rest = node
    parent = rig.pose.bones[parent_name]
    local = parent_rest.inverted() @ rest
    action = rig.animation_data.action if rig.animation_data else None
    if action and any(c.data_path.startswith(f'pose.bones["{name}"].') for c in action.fcurves):
        # Track values are absolute locals in the parent node's (scaled) frame; the importer
        # applied them to unscaled bones, so read them back in unscaled node frames.
        bone = rig.pose.bones[name]
        local = (parent.matrix @ parent.bone.matrix_local.inverted() @ unscaled(parent_rest)).inverted() @ (
            bone.matrix @ bone.bone.matrix_local.inverted() @ unscaled(rest))
    weapon.matrix_world = rig.matrix_world @ parent.matrix @ parent.bone.matrix_local.inverted() @ parent_rest @ local
    bpy.context.view_layer.update()


# View directions for the sheathed weapon (actors face +Y, +X is their right): from behind
# for back nodes, from the side of the vanilla hip node (WeaponSword/WeaponDagger left,
# WeaponAxe/WeaponMace right).
SHEATH_VIEWS = {'sword': (-3, -1, .5), 'dagger': (-3, -1, .5), 'waraxe': (3, -1, .5), 'mace': (3, -1, .5),
                'greatsword': (.8, -3, .6), 'battleaxe': (.8, -3, .6), 'warhammer': (.8, -3, .6), 'staff': (.8, -3, .6)}


def frame_camera(camera, objects, direction, margin=1.15):
    """Orthographic view of the objects' bounds from a direction in world space."""
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center, size = (low + high) / 2, max((high - low).length, .2)
    camera.location = center + Vector(direction).normalized() * size * 3
    aim(camera, center)
    bpy.context.view_layer.update()  # matrix_world is stale until the view layer updates
    view = camera.matrix_world.to_3x3().inverted()
    local = [view @ (p - center) for p in points]
    width = max(p.x for p in local) - min(p.x for p in local)
    height = max(p.y for p in local) - min(p.y for p in local)
    camera.data.ortho_scale = max(height, width * 900 / 720) * margin  # portrait: the scale is the height


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--animation", choices=("original", "rest", "walk", "attack", "sheathed"), default="rest")
    # Original weapon outside this output (wizard preview); by default the delivered weapon.nif.
    parser.add_argument('--weapon-nif', type=Path)
    parser.add_argument('--weapon-textures', type=Path, help='PNGs decoded from the weapon DDS')
    parser.add_argument('--weapon-kind')
    parser.add_argument('--weapon-preview', help='render weapon-<name>-{drawn,hand,sheathed}.png only')
    parser.add_argument("--wardrobe", default="initial", help="initial, all, underwear, without:<garment-id>")
    parser.add_argument('--hide-face', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--hide-hair', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--keep-clothes', action='store_true')
    parser.add_argument('--head-closeup', action='store_true')
    parser.add_argument('--physics-frame', type=int)
    parser.add_argument('--toon', action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    settings = load_settings(output)
    toon_enabled = settings.toon_enabled if args.toon is None else args.toon
    refs = reference_root(output)
    original_weapon = None
    if args.weapon_nif:
        original_weapon = {'nif': args.weapon_nif.resolve(), 'textures': args.weapon_textures.resolve(),
                           'kind': args.weapon_kind}
    elif settings.weapon_mode == 'original':
        original_weapon = {'nif': output / 'mod/meshes' / settings.asset_dir / 'weapon.nif',
                           'textures': output / 'dds-preview', 'kind': settings.original_weapon['kind']}
    if (args.animation == 'sheathed' or args.weapon_preview) and original_weapon is None:
        raise ValueError('Sheathed and weapon previews need an original weapon')
    if args.weapon_preview and (args.animation != 'rest' or args.wardrobe != 'initial'):
        raise ValueError('Weapon previews use the initial wardrobe and their own poses')
    if original_weapon is not None:
        from weapon_nif import SHEATH_NODES
        if original_weapon['kind'] not in SHEATH_NODES:
            raise ValueError('Unknown original weapon kind: ' + str(original_weapon['kind']))
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
    from equipment_textures import prepare_preview_assets
    preview_assets = prepare_preview_assets(output, [output/'mod/meshes'/settings.asset_dir/p['file'] for p in parts])
    if preview_assets:
        bpy.context.preferences.filepaths.texture_directory = str(preview_assets)
        bpy.context.preferences.addons['io_scene_nifly'].preferences.sky_texture_path_1 = str(output/'mod')
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
    if args.animation in ("attack", "sheathed") or args.weapon_preview:
        from custom_skeleton import NifFile
        from weapon_nif import HOLD_NODE, SHEATH_NODES
        with NifFile(str(skel)) as skeleton_file:
            add_attachment_bones(rig, skeleton_file, [HOLD_NODE, *SHEATH_NODES.values()])
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
            from equipment_textures import preview_image
            image.filepath = str(preview_image(output, image.filepath))
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
                from equipment_textures import preview_image
                path = preview_image(output, image.filepath)
                if path.exists():
                    image.filepath = str(path)
                    image.reload()
        if toon_enabled:
            from toon_preview import apply_toon_preview
            apply_toon_preview(output)
    else:
        if toon_enabled:
            from toon_preview import apply_toon_preview
            apply_toon_preview(output, meshes)
        if args.animation in ("walk", "attack") or args.weapon_preview:
            bpy.ops.object.select_all(action="DESELECT")
            rig.select_set(True)
            bpy.context.view_layer.objects.active = rig
            base = refs / "meshes/actors/character"
            if args.weapon_preview:
                from weapon_nif import DRAWN_IDLES
                animation = base / "animations" / DRAWN_IDLES[original_weapon['kind']]
            else:
                animation = base / (f"animations/{settings.sex}/mt_walkforward.hkx" if args.animation == "walk"
                                    else "animations/1hm_attackright.hkx")
            bpy.ops.import_scene.pynifly_hkx(filepath=str(animation), rename_bones=False,
                                           reference_skel=str(base / "character assets/skeleton.hkx"))
            frames = [1] if args.weapon_preview else [1, 8, 16, 24] if args.animation == "walk" else [1, 5, 10, 16]
    weapon = weapon_meshes = weapon_node_name = None
    if original_weapon is not None and (args.animation in ("attack", "sheathed") or args.weapon_preview):
        from custom_skeleton import NifFile
        from weapon_nif import HOLD_NODE, SHEATH_NODES
        with NifFile(str(skel)) as skeleton_file:
            hold_node = attachment_node(skeleton_file, HOLD_NODE)
            sheath_node = attachment_node(skeleton_file, SHEATH_NODES[original_weapon['kind']])
        weapon, weapon_meshes = import_original_weapon(original_weapon['nif'], original_weapon['textures'])
        weapon_node = sheath_node if args.animation == "sheathed" else hold_node
        weapon_node_name = SHEATH_NODES[original_weapon['kind']] if args.animation == "sheathed" else HOLD_NODE
    elif args.animation == "attack":
        from custom_skeleton import NifFile
        with NifFile(str(skel)) as skeleton_file:
            weapon_node, weapon_node_name = attachment_node(skeleton_file, "WEAPON"), "WEAPON"
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
    from blender_meshes import render_material_queues
    weapon_report = {"steel_sword_geometry": weapon is not None and original_weapon is None,
                     "original_weapon": str(original_weapon['nif']) if weapon is not None and original_weapon else None,
                     "weapon_attachment": weapon_node_name, "weapon_material": None if weapon is None else
                     "neutral metal preview" if original_weapon is None else "decoded delivered weapon DDS"}
    if args.weapon_preview:
        name = args.weapon_preview
        scene.frame_set(frames[0])
        attach(weapon, rig, hold_node)
        frame_camera(camera, meshes + weapon_meshes, (1.8, 4, .55))
        scene.render.filepath = str(previews / f"weapon-{name}-drawn.png")
        render_material_queues(scene)
        hand = rig.pose.bones[hold_node[1]]
        center = rig.matrix_world @ hand.head
        camera.location = center + Vector((.5, 1.0, .35))
        camera.data.ortho_scale = .32
        aim(camera, center)
        scene.render.filepath = str(previews / f"weapon-{name}-hand.png")
        render_material_queues(scene)
        rig.animation_data_clear()
        for bone in rig.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        attach(weapon, rig, sheath_node)
        frame_camera(camera, meshes + weapon_meshes, SHEATH_VIEWS[original_weapon['kind']])
        scene.render.filepath = str(previews / f"weapon-{name}-sheathed.png")
        render_material_queues(scene)
        (previews / f"weapon-{name}.json").write_text(json.dumps({
            "nifs": nifs, "weapon_nif": str(original_weapon['nif']), "kind": original_weapon['kind'],
            "drawn_animation": animation.name, "frame": frames[0], "hold_node": HOLD_NODE,
            "sheath_node": SHEATH_NODES[original_weapon['kind']],
            "images": [f"weapon-{name}-{view}.png" for view in ("drawn", "hand", "sheathed")],
            "weapon_material": "decoded delivered weapon DDS", "game_verified": False}, indent=2), encoding="utf-8")
        return
    if args.animation == "sheathed":
        attach(weapon, rig, weapon_node)
        frame_camera(camera, meshes + weapon_meshes, SHEATH_VIEWS[original_weapon['kind']])
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
            attach(weapon, rig, weapon_node)
        scene.render.filepath = str(previews / f"{prefix}-{frame:02}.png")
        render_material_queues(scene)
    if weapon is not None and args.animation == "attack":
        scene.frame_set(10)
        hand = rig.pose.bones[weapon_node[1]]
        attach(weapon, rig, weapon_node)
        center = rig.matrix_world @ hand.head
        camera.location = center + Vector((.5, 1.0, .35))
        camera.data.ortho_scale = .32
        aim(camera, center)
        scene.render.filepath = str(previews / ("attack-hand-10.png" if wardrobe == "initial" else prefix + "-hand-10.png"))
        render_material_queues(scene)
    (previews / f"{prefix}.json").write_text(json.dumps({
        "nifs": nifs, "animation": args.animation, "frames": frames, "wardrobe": wardrobe,
        "meshes": [obj.name for obj in meshes], "game_verified": False, **weapon_report,
    }, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / f"preview-{prefix}.blend"))


if __name__ == "__main__":
    main()
