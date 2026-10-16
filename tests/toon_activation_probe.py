"""Build an activation-only diagnostic from the delivered Prototype 2 ZIP.

Keep pending face/composite experiments out of this comparison. No deployed
game files or shader caches are changed. Run on Windows with FXC/MSVC/D3D11.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
from PIL import Image

from toon_gpu_fixture import build


def verify(baseline, shader_root, scene_root, output):
    output.mkdir(parents=True, exist_ok=True)
    old_guard = 'defined(SKINNED) && !defined(TRUE_PBR)'
    new_guard = '!defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)'
    with zipfile.ZipFile(baseline) as archive:
        assert archive.testzip() is None
        files = {name: archive.read(name) for name in archive.namelist()}
    lighting = files['Shaders/Lighting.hlsl'].decode('utf8')
    metadata = json.loads(files['Shaders/VRM2Skyrim/adapter.json'])
    assert metadata['prototype'] == 2 and metadata['diagnostic'] is True
    assert hashlib.sha256(lighting.encode('utf8')).hexdigest() == metadata['patched_lighting_sha256']
    assert hashlib.sha256((shader_root/'Lighting.hlsl').read_bytes()).hexdigest() == metadata['lighting_sha256']
    assert lighting.count(old_guard) == 6
    assert len(files) == 7
    patched = lighting.replace(old_guard, new_guard).encode('utf8')
    files['Shaders/Lighting.hlsl'] = patched
    metadata.update(activation_probe=1, patched_lighting_sha256=hashlib.sha256(patched).hexdigest(),
                    scope='non-landscape non-PBR Glowmap material with exact 8x4 DDS signature')
    files['Shaders/VRM2Skyrim/adapter.json'] = json.dumps(metadata, indent=2).encode('utf8')
    files['Shaders/VRM2Skyrim/README.md'] = (
        '# Activation check / 適用確認\n\n'
        'Skyrimを終了し、他のトゥーン試作MODを無効化してください。\n'
        'この版を導入し、Community Shadersより優先してDeployします。\n'
        'Data/ShaderCacheを別名へ変更し、SKSEから再起動してください。\n'
        'VRM部分がピンクになれば適用されています。フォロワーの再出力は不要です。\n\n'
        'Exit Skyrim, disable other toon prototypes, and deploy this mod after\n'
        'Community Shaders. Rename Data/ShaderCache and relaunch through SKSE.\n'
        'Recognized VRM surfaces turn pink. No follower re-export is needed.\n'
    ).encode('utf8')
    folder = output/'mod'
    for name, value in files.items():
        path = folder/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    package = output/'VRM2Skyrim-Toon-Activation-Check-1.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(files.items()):
            archive.writestr(name, value)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None and len(archive.namelist()) == 7
        assert all(archive.read(name) == value for name, value in files.items())

    fxc = 'C:/Program Files (x86)/Windows Kits/10/bin/10.0.22621.0/x64/fxc.exe'
    features = ('DYNAMIC_CUBEMAPS', 'IBL', 'LIGHT_LIMIT_FIX', 'SKYLIGHTING',
                'SCREEN_SPACE_GI', 'SCREEN_SPACE_SHADOWS', 'WETNESS_EFFECTS',
                'EXTENDED_MATERIALS', 'VOLUMETRIC_SHADOWS', 'EXP_HEIGHT_FOG',
                'VANILLA_FRESNEL', 'EXTENDED_TRANSLUCENCY', 'ISL')
    variants = []
    for skinned in [False, True]:
        for name, extra in [('forward', ()), ('cutout', ('DO_ALPHA_TEST',)),
                            ('deferred', ('DEFERRED',)),
                            ('features', features), ('features-deferred', ('DEFERRED',)+features)]:
            variants.append((name+('-skinned' if skinned else ''), 'ps_5_0',
                             ('PSHADER',)+(('SKINNED',) if skinned else ())+extra))
    variants += [
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

    def compile_shader(source, destination, target, flags):
        args = [fxc, '/nologo', '/T', target, '/E', 'main', '/I', str(folder/'Shaders'),
                '/I', str(shader_root), '/Fo', str(destination)]
        for flag in flags:
            args += ['/D', flag+'=1']
        result = subprocess.run([*args, str(source)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        return hashlib.sha256(destination.read_bytes()).hexdigest()

    def compile_pair(variant):
        name, target, flags = variant
        original = compile_shader(shader_root/'Lighting.hlsl', output/(name+'-original.cso'), target, flags)
        probe = compile_shader(folder/'Shaders/Lighting.hlsl', output/(name+'-probe.cso'), target, flags)
        excluded = bool({'TRUE_PBR', 'LANDSCAPE', 'LODLANDSCAPE'} & set(flags)) or target.startswith('vs')
        assert not excluded or original == probe, name
        return {'name': name, 'defines': flags, 'excluded': excluded, 'identical': original == probe}

    with ThreadPoolExecutor(max_workers=4) as pool:
        compiled = list(pool.map(compile_pair, variants))
    (output/'old-gate.hlsl').write_text(lighting, encoding='utf8')
    compile_shader(output/'old-gate.hlsl', output/'old-gate.cso', 'ps_5_0', ('PSHADER', 'DO_ALPHA_TEST'))
    # Use the exact old helper files for both shaders; the ZIP carries them.
    build(output)
    reports = {}
    for variant, shader in [('old-gate', output/'old-gate.cso'), ('probe', output/'cutout-probe.cso')]:
        renders = output/('render-'+variant)
        result = subprocess.run([str(output/'toon_gpu.exe'), str(scene_root/'base.scene'),
                                 str(scene_root/'marked.scene'), str(output/'cutout-original.cso'),
                                 str(shader), str(renders), '--diagnostic'], capture_output=True, text=True)
        report = json.loads((renders/'activation-verification.json').read_text(encoding='utf8'))
        assert report['unmarked_max_byte_error'] == report['fallback_max_byte_error'] == 0
        assert result.returncode == (1 if variant == 'old-gate' else 0), result.stdout+result.stderr
        assert (report['pink_pixels'] == 0) if variant == 'old-gate' else (report['pink_pixels'] > 1000)
        reports[variant] = report
    old = np.asarray(Image.open(output/'render-old-gate/toon.ppm'))
    original = np.asarray(Image.open(output/'render-old-gate/original.ppm'))
    assert np.array_equal(old, original)
    record = {'compiled': compiled, 'gpu': reports, 'old_gate_matches_original': True,
              'zip_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
              'live_game_activation': 'awaiting observation'}
    (output/'verification.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    print('PASS:', len(compiled), 'shader pairs; old gate inactive, probe pink; ordinary pixels unchanged')
    print(package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--shader-root', type=Path, required=True)
    parser.add_argument('--scene-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(*(getattr(args, name).resolve() for name in ['baseline', 'shader_root', 'scene_root', 'output']))
