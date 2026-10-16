"""Compile actual Community Shaders permutations; never installs the result."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toon import shader_package  # noqa: E402


def verify(shader_root, output, diagnostic=False):
    shader_root, output = Path(shader_root).resolve(), Path(output).resolve()
    shader_package(shader_root, output, diagnostic)
    patched_folder = 'shader-diagnostic-mod' if diagnostic else 'shader-mod'
    fxc = Path('C:/Program Files (x86)/Windows Kits/10/bin/10.0.22621.0/x64/fxc.exe')
    feature_flags = ('DYNAMIC_CUBEMAPS', 'IBL', 'LIGHT_LIMIT_FIX', 'SKYLIGHTING',
                     'SCREEN_SPACE_GI', 'SCREEN_SPACE_SHADOWS', 'WETNESS_EFFECTS',
                     'EXTENDED_MATERIALS', 'VOLUMETRIC_SHADOWS', 'EXP_HEIGHT_FOG',
                     'VANILLA_FRESNEL', 'EXTENDED_TRANSLUCENCY', 'ISL')
    variants = [
        ('forward', 'ps_5_0', ('PSHADER', 'SKINNED')),
        ('glow', 'ps_5_0', ('PSHADER', 'SKINNED', 'GLOWMAP')),
        ('cutout', 'ps_5_0', ('PSHADER', 'SKINNED', 'DO_ALPHA_TEST')),
        ('deferred', 'ps_5_0', ('PSHADER', 'SKINNED', 'DEFERRED')),
        ('deferred-cutout', 'ps_5_0', ('PSHADER', 'SKINNED', 'DEFERRED', 'DO_ALPHA_TEST')),
        ('reflection-deferred', 'ps_5_0', ('PSHADER', 'SKINNED', 'DEFERRED', 'SPECULAR', 'DYNAMIC_CUBEMAPS', 'VANILLA_FRESNEL')),
        ('features', 'ps_5_0', ('PSHADER', 'SKINNED')+feature_flags),
        ('features-deferred', 'ps_5_0', ('PSHADER', 'SKINNED', 'DEFERRED')+feature_flags),
        ('ordinary', 'ps_5_0', ('PSHADER',)),
        ('unskinned-cutout', 'ps_5_0', ('PSHADER', 'DO_ALPHA_TEST')),
        ('unskinned-deferred', 'ps_5_0', ('PSHADER', 'DEFERRED')),
        ('unskinned-features-deferred', 'ps_5_0', ('PSHADER', 'DEFERRED')+feature_flags),
        ('skin', 'ps_5_0', ('PSHADER', 'SKINNED', 'FACEGEN_RGB_TINT', 'CS_SKIN')),
        ('hair', 'ps_5_0', ('PSHADER', 'SKINNED', 'HAIR', 'CS_HAIR')),
        ('eye', 'ps_5_0', ('PSHADER', 'SKINNED', 'EYE')),
        ('pbr', 'ps_5_0', ('PSHADER', 'SKINNED', 'TRUE_PBR', 'DEFERRED')),
        ('landscape', 'ps_5_0', ('PSHADER', 'LANDSCAPE', 'DEFERRED')),
        ('lod-landscape', 'ps_5_0', ('PSHADER', 'LODLANDSCAPE')),
        ('pbr-landscape', 'ps_5_0', ('PSHADER', 'LANDSCAPE', 'TRUE_PBR', 'DEFERRED')),
        ('skinned-vertex', 'vs_5_0', ('VSHADER', 'SKINNED')),
        ('ordinary-vertex', 'vs_5_0', ('VSHADER',)),
    ]
    def compile_variant(variant):
        name, target, flags = variant
        results = []
        for kind, folder in [('original', shader_root), ('toon', output/patched_folder/'Shaders')]:
            path = output/f'{kind}-{name}.cso'
            args = [str(fxc), '/nologo', '/T', target, '/E', 'main',
                    '/I', str(output/patched_folder/'Shaders'), '/I', str(shader_root), '/Fo', str(path)]
            for flag in flags:
                args += ['/D', flag+'=1']
            args.append(str(folder/'Lighting.hlsl'))
            process = subprocess.run(args, capture_output=True, text=True)
            if process.returncode:
                raise RuntimeError(name+' '+kind+'\n'+process.stdout+'\n'+process.stderr)
            results.append(hashlib.sha256(path.read_bytes()).hexdigest())
        excluded = bool({'TRUE_PBR', 'LANDSCAPE', 'LODLANDSCAPE'} & set(flags)) or target.startswith('vs')
        if excluded and results[0] != results[1]:
            raise ValueError('Non-target permutation bytecode changed: '+name)
        return {'variant': name, 'defines': flags, 'compiled': True,
                'excluded': excluded, 'bytecode_identical': results[0] == results[1]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(compile_variant, variants))
    (output/'compile-verification.json').write_text(json.dumps(results, indent=2), encoding='utf8')
    composites = []
    for name, flags in [('ssgi', ('SSGI',)), ('plain', ()),
                        ('features', ('SSGI', 'DYNAMIC_CUBEMAPS', 'IBL', 'SKYLIGHTING')),
                        ('reverse-z', ('SSGI', 'REVERSE_Z')), ('terrain', ('SSGI', 'TERRAIN_BLENDING'))]:
        hashes = []
        for kind, folder in [('original', shader_root), ('toon', output/patched_folder/'Shaders')]:
            path = output/f'{kind}-composite-{name}.cso'
            args = [str(fxc), '/nologo', '/T', 'cs_5_0', '/E', 'main',
                    '/D', 'CSHADER=1',
                    '/I', str(output/patched_folder/'Shaders'), '/I', str(shader_root), '/Fo', str(path)]
            for flag in flags:
                args += ['/D', flag+'=1']
            process = subprocess.run([*args, str(folder/'DeferredCompositeCS.hlsl')], capture_output=True, text=True)
            if process.returncode:
                raise RuntimeError('composite '+name+' '+kind+'\n'+process.stdout+'\n'+process.stderr)
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        if not flags and hashes[0] != hashes[1]:
            raise ValueError('Composite without SSGI changed')
        composites.append({'variant': name, 'defines': flags, 'compiled': True, 'bytecode_identical': hashes[0] == hashes[1]})
    (output/'composite-compile-verification.json').write_text(json.dumps(composites, indent=2), encoding='utf8')
    print('PASS:', len(results), 'original/patched CS permutations;', sum(r['excluded'] for r in results),
          'excluded permutations byte-identical', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--shader-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true')
    args = parser.parse_args()
    verify(args.shader_root, args.output, args.diagnostic)
