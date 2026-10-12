"""Keep displaced original skin inside standard-slot VRM clothes."""
import argparse
import json
import logging
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'dependencies'))
from settings import load_settings  # noqa: E402
from fit_armor_blender import submesh, select  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args(sys.argv[sys.argv.index('--')+1:]).output.resolve()
    settings = load_settings(output)
    root = output/'mod/meshes'/settings.asset_dir
    manifest = json.loads((output/'appearance.json').read_text(encoding='utf8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module='io_scene_nifly')
    rig = None

    def load(path):
        nonlocal rig
        before = set(bpy.context.scene.objects)
        bpy.context.view_layer.objects.active = None
        bpy.ops.import_scene.pynifly(filepath=str(path), rename_bones=False, create_bones=True,
                                   reference_skel=str(root/'skeleton.nif'), import_animations=False,
                                   import_shapekeys=False, import_collisions=False)
        imported = [o for o in bpy.context.scene.objects if o not in before]
        armature = next(o for o in imported if o.type == 'ARMATURE')
        meshes = [o for o in imported if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
        if rig is None:
            rig = armature
        else:
            for obj in meshes:
                for group in obj.vertex_groups:
                    if group.name.startswith('SBP_'):
                        continue
                    if group.name not in rig.data.bones or not np.allclose(
                            np.asarray(armature.data.bones[group.name].matrix_local),
                            np.asarray(rig.data.bones[group.name].matrix_local), atol=.001):
                        raise ValueError('Standard clothing skin has a different bind pose: '+group.name)
                world = obj.matrix_world.copy()
                obj.parent = rig
                obj.matrix_world = world
                for modifier in obj.modifiers:
                    if modifier.type == 'ARMATURE':
                        modifier.object = rig
            bpy.data.objects.remove(armature, do_unlink=True)
        return meshes

    # Complete original body rig contains fingers/toes omitted by a torso-only import.
    body = load(output/'armor-source/body.nif')
    for obj in body:
        bpy.data.objects.remove(obj, do_unlink=True)
    before = set(bpy.context.scene.objects)
    bpy.context.view_layer.objects.active = None
    bpy.ops.import_scene.pynifly(filepath=str(root/'skeleton.nif'), rename_bones=False, create_bones=False,
                               import_animations=False, import_shapekeys=False, import_collisions=False)
    full = next(o for o in bpy.context.scene.objects if o not in before and o.type == 'ARMATURE')
    for bone in rig.data.bones:
        if not np.allclose(np.asarray(rig.matrix_world @ bone.matrix_local),
                           np.asarray(full.matrix_world @ full.data.bones[bone.name].matrix_local), atol=.001):
            raise ValueError('Standard clothing skeleton changes the original body bind pose')
    bpy.data.objects.remove(rig, do_unlink=True)
    rig = full
    for part in manifest['components']:
        if part['role'] != 'garment' or part['slot'] not in (32, 33, 34, 37, 38):
            continue
        clothing = load(root/part['file'])
        copies = []
        slots = part.get('slots', [part['slot']])
        sources = (['body.nif', 'hands.nif', 'feet.nif'] if part.get('item_kind') == 'full' and part['slot'] == 32
                   else ['hands.nif' if part['slot'] == 33 else 'feet.nif' if part['slot'] == 37 else 'body.nif'])
        skin = [obj for source in sources for obj in load(root/source)]
        for obj in skin:
            for slot in slots:
                group = next((g for g in obj.vertex_groups if g.name.startswith(f'SBP_{slot}_')), None)
                if group is None:
                    continue
                faces = [p.index for p in obj.data.polygons if all(any(g.group == group.index and g.weight > .5
                         for g in obj.data.vertices[v].groups) for v in p.vertices)]
                if faces:
                    copies.append(submesh(obj, faces, 'V2SClothingSkin_'+obj.name+'_'+str(slot), slot, rig))
        # PyNifly exports a selected rig's parented meshes too. Retire the
        # imported originals before exporting the explicitly retained copies.
        for obj in skin:
            bpy.data.objects.remove(obj, do_unlink=True)
        logging.info('Standard clothing export meshes: %s', [o.name for o in clothing+copies])
        select(clothing+copies+[rig], rig)
        bpy.ops.export_scene.pynifly(filepath=str(root/part['file']), target_game='SKYRIMSE', rename_bones=False,
                                   blender_xf=False, preserve_hierarchy=True, export_modifiers=False,
                                   export_animations=False, export_colors=True, intuit_defaults=False)
        part['retained_skin'] = True
        logging.info('Standard garment retained original skin: %s, slots=%s, shapes=%s', part['id'], slots, len(copies))
        for obj in clothing+copies:
            bpy.data.objects.remove(obj, do_unlink=True)
    (output/'appearance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
