"""Export native NIF/DDS inputs and build the offscreen production-shader fixture."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from custom_skeleton import NifFile, children  # noqa: E402
from settings import load_settings  # noqa: E402


def scene(output, destination, unmarked=False):
    output = Path(output)
    settings = load_settings(output)
    manifest = json.loads((output/'appearance.json').read_text(encoding='utf8'))
    data = []
    for part in manifest['components']:
        with NifFile(str((output/'mod/meshes'/settings.asset_dir/part['file']).resolve())) as nif:
            by_id = {s.id: s for s in nif.shapes}
            shapes = [by_id[i] for i in children(nif, nif.rootNode) if i in by_id]
            if len(shapes) != len(nif.shapes):
                raise ValueError('Fixture expects direct appearance shape children')
            for shape in shapes:
                if shape.name.startswith('V2SCollision_'):
                    continue
                flags = shape.alpha_property.properties.flags if shape.has_alpha_property else 0
                threshold = shape.alpha_property.properties.threshold if shape.has_alpha_property else 0
                props = shape.shader.properties
                if unmarked and props.Shader_Type == 2:
                    marker = shape.shader.textures.get('Glow', '')
                    if marker and Path(marker.replace('\\', '/')).name.startswith('toon_'):
                        raise ValueError('Comparison base contains toon markers; use the original unmarked export')
                if props.Shader_Flags_2 & 16:
                    flags |= 1 << 20
                vertices = np.column_stack((shape.verts, shape.normals, shape.uvs)).astype('<f4')
                indices = np.asarray(shape.tris, dtype='<u4').ravel()
                blob = bytearray(struct.pack('<5If', len(vertices), len(indices), props.Shader_Type,
                                             flags, threshold, props.Alpha))
                for name in ('Diffuse', 'Normal', 'Glow'):
                    relative = shape.shader.textures.get(name)
                    path = str((output/'mod'/relative.replace('\\', '/')).resolve()) if relative else ''
                    value = path.encode('utf8')
                    blob += struct.pack('<I', len(value))+value
                blob += vertices.tobytes()+indices.tobytes()
                data.append(blob)
    Path(destination).write_bytes(struct.pack('<II', 0x32535456, len(data))+b''.join(data))
    print('Native scene:', destination, len(data), 'shapes', flush=True)


def build(output):
    compiler_root = Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC')
    msvc = sorted(compiler_root.iterdir())[-1]
    kits = Path('C:/Program Files (x86)/Windows Kits/10')
    sdk = '10.0.22621.0'
    binary = msvc/'bin/Hostx64/x64'
    env = dict(os.environ)
    env['PATH'] = str(binary)+os.pathsep+env['PATH']
    env['LIB'] = os.pathsep.join(map(str, (msvc/'lib/x64', kits/'Lib'/sdk/'um/x64', kits/'Lib'/sdk/'ucrt/x64')))
    args = [str(binary/'cl.exe'), '/nologo', '/EHsc', '/std:c++20', '/O2', '/MD', '/DNOMINMAX',
            '/DWIN32_LEAN_AND_MEAN', '/I'+str(msvc/'include')]
    for folder in ('um', 'shared', 'ucrt', 'winrt'):
        args += ['/I'+str(kits/'Include'/sdk/folder)]
    args += [str(ROOT/'tests/toon_gpu.cpp'), '/Fo'+str(output/'toon_gpu.obj'),
             '/Fe'+str(output/'toon_gpu.exe'), '/link', 'd3d11.lib', 'd3dcompiler.lib', 'dxgi.lib', 'dxguid.lib']
    subprocess.run(args, env=env, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--marked', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiled-shaders', type=Path,
                        help='compile_toon.py output; defaults to the parent of --output')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    scene(args.base, args.output/'base.scene', unmarked=True)
    scene(args.marked, args.output/'marked.scene')
    build(args.output)
    shaders = (args.compiled_shaders or args.output.parent).resolve()
    subprocess.run([str(args.output/'toon_gpu.exe'), str(args.output/'base.scene'),
                    str(args.output/'marked.scene'), str(shaders/'original-cutout.cso'),
                    str(shaders/'toon-cutout.cso'), str(args.output/'renders')], check=True)
