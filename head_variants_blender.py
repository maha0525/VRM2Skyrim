"""Export one permanent-layer model for each independent face/hair policy."""
import argparse
import logging
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'dependencies'))
from settings import load_settings  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args(sys.argv[sys.argv.index('--')+1:]).output.resolve()
    settings = load_settings(output)
    bpy.ops.preferences.addon_enable(module='io_scene_nifly')
    bpy.ops.wm.open_mainfile(filepath=str(output/'converted.blend'))
    from gear_head_runtime import head_variants
    from convert_blender import select_only
    from inspect_vrm import read_glb
    from nif_materials import apply_alpha
    from custom_skeleton import NifFile
    document, _ = read_glb(output/'source.glb')
    materials = {m['name']: m for m in document['materials']}
    variants = [{'file': 'fixed_full.nif', 'nodes': settings.appearance_parts['fixed']}, *head_variants(settings)]
    for variant in variants:
        if not variant['nodes']:
            continue
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and
                  o.get('v2s_source_node') in variant['nodes'] and o.get('v2s_part') in ('fixed', 'face', 'hair')]
        rig = next(m.object for o in meshes for m in o.modifiers if m.type == 'ARMATURE')
        select_only(meshes+[rig], rig)
        path = output/'mod/meshes'/settings.asset_dir/variant['file']
        bpy.ops.export_scene.pynifly(filepath=str(path), target_game='SKYRIMSE', rename_bones=False,
                                   blender_xf=False, preserve_hierarchy=True, export_modifiers=False,
                                   export_animations=False, export_colors=True, intuit_defaults=False)
        apply_alpha(path, {o.name: materials[o.material_slots[0].material.name] for o in meshes})
        with NifFile(str(path)) as nif:
            for shape in nif.shapes:
                for slot, texture in shape.textures.items():
                    if texture.lower().endswith('.png'):
                        shape.set_texture(slot, texture[:-4]+'.dds')
            nif.save()
        logging.info('Permanent head variant: %s (%s original shapes)', path.name, len(meshes))


if __name__ == '__main__':
    main()
