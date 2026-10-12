"""Outfit Studio edit kits and persistent, rig-preserving shape-only overrides."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil
import tempfile
import zipfile

import numpy as np

from settings import load_settings

ROOT = Path(__file__).parent
LOG = logging.getLogger(__name__)


def override_path(avatar, key):
    if len(avatar) != 64 or len(key) != 16 or any(c not in '0123456789abcdef' for c in avatar+key):
        raise ValueError('Invalid equipment edit identity')
    return ROOT/'build/equipment-overrides'/avatar/(key+'.npz')


def export_kit(output):
    output = Path(output)
    settings = load_settings(output)
    profile = json.loads((output/'armor-fitting.json').read_text())
    root = output/'mod/meshes'/settings.asset_dir
    files = {i['file'] for i in profile['equipment']}
    archive = output/'OutfitStudio-EditKit.zip'
    instructions = '''Outfit Studioでの仕上げ

1. このZIPを展開します。Outfit Studioのゲーム設定をSkyrim Special Editionにします。
2. File > Load Outfitで、Data/meshes内のfitted_*_1.nifを開きます。
3. File > Load Referenceで同じフォルダのbody-reference.nifを読み込みます。
   骨格を読み込む場合は付属のskeleton.nifを使用してください。
4. ブラシで服の形だけを直します。頂点・面の追加/削除、形の名前変更、
   重量/UVの変更、標準体型への骨格交換はしないでください。
5. File > Export > To NIFで、参照身体を含めず別のNIFへ書き出します。
6. 変換結果画面の「仕上げた装備を戻す」で対応する装備を選び、そのNIFを読み込みます。
   CLIでは: python outfit_edits.py --output <変換フォルダ> --mesh-key <manifestのsource_key> --edited <NIF> --blender <Blender.exe>

取り込むのは服の頂点と法線です。元の骨格、ウェイト、UV、素材、装備枠を保持します。
OriginalSkin_で始まる身体は変更しないでください。編集はこのVRM用に保存され、
次の変換で同じ装備を選ぶと再利用されます。元VRMや別アバターには影響しません。
'''
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        target.writestr('README.txt', instructions)
        target.writestr('manifest.json', json.dumps(profile, ensure_ascii=False, indent=2))
        for name in sorted(files | {'skeleton.nif'}):
            target.write(root/name, 'Data/meshes/'+settings.asset_dir+'/'+name)
        target.write(output/'armor-source/body.nif', 'Data/meshes/'+settings.asset_dir+'/body-reference.nif')
        for name in ('face.nif', 'hair.nif'):
            if (root/name).is_file():
                target.write(root/name, 'Data/meshes/'+settings.asset_dir+'/'+name)
        for path in sorted((output/'mod/textures'/settings.asset_dir).rglob('*.dds')):
            target.write(path, 'Data/'+path.relative_to(output/'mod').as_posix())
    LOG.info('Outfit Studio edit kit: %s unique equipment meshes', len(files))
    return archive


def import_edit(output, mesh_key, edited):
    from custom_skeleton import NifFile
    output = Path(output)
    settings = load_settings(output)
    profile = json.loads((output/'armor-fitting.json').read_text())
    item = next((i for i in profile['equipment'] if i.get('source_key') == mesh_key), None)
    if item is None:
        raise ValueError('Choose equipment belonging to this conversion')
    base = output/'mod/meshes'/settings.asset_dir/item['file']
    arrays, names = {}, []
    with NifFile(str(base)) as original, NifFile(str(edited)) as changed:
        old = {s.name: s for s in original.shapes}
        new = {s.name: s for s in changed.shapes}
        if old.keys() != new.keys():
            raise ValueError('装備の形名が変わっています。参照身体を除いて書き出してください')
        for index, (name, shape) in enumerate(old.items()):
            replacement = new[name]
            if shape.tris != replacement.tris or not np.allclose(shape.uvs, replacement.uvs, atol=1e-5) or len(shape.verts) != len(replacement.verts):
                raise ValueError('頂点・面・UVが変更されています。形だけを編集してください')
            points, normals = np.asarray(replacement.verts), np.asarray(replacement.normals)
            if not np.isfinite(points).all() or not np.isfinite(normals).all():
                raise ValueError('Edited geometry contains invalid coordinates')
            if name.startswith('OriginalSkin_') and (not np.allclose(shape.verts, points, atol=.001) or
                                                     not np.allclose(shape.normals, normals, atol=.001)):
                raise ValueError('OriginalSkin_の身体・法線を変更しないでください')
            names.append(name)
            arrays[f'original_{index}'] = np.asarray(shape.verts)
            arrays[f'uv_{index}'] = np.asarray(shape.uvs)
            arrays[f'points_{index}'] = points
            arrays[f'normals_{index}'] = normals
    path = override_path(settings.appearance_source_sha256, mesh_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        # Subsequent edits start from an already finished output. Keep the initial
        # converter coordinates as the regeneration reference.
        with np.load(path, allow_pickle=False) as previous:
            if previous['names'].tolist() != names:
                raise ValueError('Saved edit shape order changed')
            for index in range(len(names)):
                arrays[f'original_{index}'] = previous[f'original_{index}'].copy()
    arrays['names'] = np.asarray(names)
    arrays['base_sha256'] = np.asarray(hashlib.sha256(base.read_bytes()).hexdigest())
    np.savez_compressed(path, **arrays)
    LOG.info('Saved shape-only equipment edit: %s (%s shapes)', mesh_key, len(names))
    return path


def apply_to_blender(objects, avatar, key):
    """Apply positions/normals before export; preserve the converter's rig and materials."""
    path = override_path(avatar, key)
    if not path.is_file():
        return False
    from mathutils.kdtree import KDTree
    with np.load(path, allow_pickle=False) as arrays:
        lookup = {name: index for index, name in enumerate(arrays['names'].tolist())}
        if set(lookup) != {obj.name for obj in objects}:
            raise ValueError('Saved finishing edit has different shapes; update the edit for this equipment')
        for obj in objects:
            if obj.name.startswith('OriginalSkin_'):
                continue  # The converter owns the exact original skin and its shading.
            index = lookup[obj.name]
            reference_uv = arrays[f'uv_{index}'].copy()
            reference_uv[:, 1] = 1. - reference_uv[:, 1]  # NIF top-left -> Blender bottom-left.
            reference = np.column_stack((arrays[f'original_{index}'], reference_uv))
            tree = KDTree(len(reference))
            for i, value in enumerate(reference):
                tree.insert(value[:3], i)
            tree.balance()
            mesh = obj.data
            points = np.asarray([v.co for v in mesh.vertices])
            uv = mesh.uv_layers.active
            corners = np.column_stack((points[[loop.vertex_index for loop in mesh.loops]],
                                       np.asarray([v.uv for v in uv.data])))
            near = np.asarray([min((i for _, i, _ in tree.find_n(value[:3], min(32, len(reference)))),
                                   key=lambda i: np.sum((reference[i]-value)**2)) for value in corners])
            distance = np.linalg.norm(reference[near]-corners, axis=1)
            if distance.max() > .02:
                raise ValueError('Saved finishing edit no longer matches this source/reference body')
            moved = arrays[f'points_{index}'][near]
            totals, count = np.zeros_like(points), np.zeros(len(points))
            for loop, value in zip(mesh.loops, moved):
                totals[loop.vertex_index] += value
                count[loop.vertex_index] += 1
            for i, vertex in enumerate(mesh.vertices):
                if count[i]:
                    vertex.co = totals[i]/count[i]
            mesh.normals_split_custom_set(arrays[f'normals_{index}'][near].tolist())
    LOG.info('Reused Outfit Studio finishing edit: %s', key)
    return True


def apply_edit(output, mesh_key, edited, blender):
    """Update the current MOD transactionally, as well as future conversions."""
    from armor_validation import validate_fitting
    from converter import package, run_blender
    from settings import VERSION
    output = Path(output).resolve()
    settings = load_settings(output)
    profile = json.loads((output/'armor-fitting.json').read_text())
    item = next((i for i in profile['equipment'] if i['source_key'] == mesh_key), None)
    if item is None:
        raise ValueError('Choose equipment belonging to this conversion')
    mesh = output/'mod/meshes'/settings.asset_dir/item['file']
    files = [mesh, mesh.with_name(mesh.name.replace('_1.nif', '_0.nif')),
             override_path(settings.appearance_source_sha256, mesh_key),
             output/'armor-fitting.json', output/'mod'/settings.asset_dir/'armor-fitting.json',
             output/'armor-validation.json', output/'package-manifest.json',
             output/f'{settings.mod_id}-VRM2Skyrim-{VERSION}.zip', output/'OutfitStudio-EditKit.zip']
    with tempfile.TemporaryDirectory(prefix='finishing-backup-', dir=output) as directory:
        backup = Path(directory)
        existed = {p for p in files if p.is_file()}
        for index, file in enumerate(files):
            if file in existed:
                shutil.copy2(file, backup/str(index))
        try:
            import_edit(output, mesh_key, edited)
            run_blender(blender, 'fit_armor_blender.py', ['--output', output, '--mesh-key', mesh_key], output, 'Import finishing edit')
            validate_fitting(output)
            archive = package(output)
            export_kit(output)
            return archive
        except Exception:
            for index, file in enumerate(files):
                if file in existed:
                    shutil.copy2(backup/str(index), file)
                else:
                    file.unlink(missing_ok=True)
            LOG.exception('Finishing edit failed; restored mesh, saved edit and archives')
            raise


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mesh-key', required=True)
    parser.add_argument('--edited', type=Path, required=True)
    parser.add_argument('--blender', type=Path, help='Also rebuild and validate the current MOD ZIP')
    args = parser.parse_args()
    print(apply_edit(args.output, args.mesh_key, args.edited, args.blender) if args.blender
          else import_edit(args.output, args.mesh_key, args.edited))
