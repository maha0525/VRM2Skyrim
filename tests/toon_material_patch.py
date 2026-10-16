"""Clone source-avatar assets; prepare/validate an authored-material patch.

No writes to the original conversion or installed game. Source textures in the
clone also allow the complete avatar to be rendered by the D3D fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from custom_skeleton import NifFile  # noqa: E402
from settings import load_settings  # noqa: E402
from toon import avatar_paths, prepare_materials, validate_toon  # noqa: E402


def geometry(path):
    with NifFile(str(path.resolve())) as nif:
        result = {}
        for shape in nif.shapes:
            if shape.name.startswith('V2SOutline_'):
                continue  # Separately validated against its explicit source owner.
            data = b''.join(np.asarray(v).tobytes() for v in [shape.verts, shape.tris, shape.normals, shape.uvs])
            data += json.dumps([shape.bone_names, shape.bone_weights], sort_keys=True).encode()
            data += bytes(shape.global_to_skin)
            for name in shape.bone_names:
                transform = shape.get_shape_skin_to_bone(name)
                if transform is not None:
                    data += bytes(transform)
            result[shape.name] = hashlib.sha256(data).hexdigest()
        return result


def build(source, output):
    settings = load_settings(source)
    manifest = json.loads((source/'appearance.json').read_text(encoding='utf8'))
    output.mkdir(parents=True, exist_ok=True)
    for name in ['source.glb', 'appearance.json', 'settings.json']:
        shutil.copy2(source/name, output/name)
    paths = avatar_paths(source, settings, manifest)
    originals, textures = {}, set()
    for path in sorted(paths):
        relative = path.relative_to(source)
        target = output/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        originals[path.name] = geometry(path)
        with NifFile(str(path.resolve())) as nif:
            for shape in nif.shapes:
                textures.update(t.replace('\\', '/') for t in shape.shader.textures.values() if t)
    for relative in textures:
        path = source/'mod'/relative
        if path.is_file():
            target = output/'mod'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    report = prepare_materials(output)
    validate_toon(output)
    changed = []
    for path in sorted(avatar_paths(output, settings, manifest)):
        assert geometry(path) == originals[path.name], path.name
        original = source/path.relative_to(output)
        if path.read_bytes() != original.read_bytes():
            changed.append(path.relative_to(output/'mod').as_posix())
    entries = [e for e in report['materials'] if e.get('profile') == 'authored_material']
    expected = {'meshes/'+settings.asset_dir+'/'+e['file'] for e in entries}
    if set(changed) != expected:
        raise ValueError('Patch changes differ from authored material owners: '+str(changed))
    selected = set(changed) | {e['control'] for e in entries}
    archive = output/(settings.mod_id+'-Toon-Materials-6.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for relative in sorted(selected):
            package.write(output/'mod'/relative, relative)
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None and set(package.namelist()) == selected
    record = {'source': str(source), 'patch': str(archive), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'size': archive.stat().st_size, 'files': sorted(selected),
              'geometry_normals_uvs_unchanged': True, 'authored_shapes': report['authored_shapes'],
              'authored_face_shapes': report['authored_face_shapes']}
    record['outline_shapes'] = report['outline_shapes']
    record['skin_weights_bind_transforms_unchanged'] = True
    (output/'material-patch-verification.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve())
