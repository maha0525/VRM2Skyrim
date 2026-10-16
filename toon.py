"""Opt-in material metadata and a version-checked Community Shaders prototype.

The metadata uses a zero-emission glow texture: the native Glowmap material
binds it at t6. The unmodified renderer therefore retains ordinary lighting.
"""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil
import struct
import zipfile

from dds import validate_dds
from settings import load_settings

ROOT = Path(__file__).resolve().parent
SIGNATURE = bytes((255, 0, 255, 255, 0, 255, 0, 255))
SUPPORTED_LIGHTING = '5cb3f71e483d6aba661f9adb10ac8d06db36878f6d6f05c4c8ec383be9fd40e8'
SUPPORTED_COMPOSITE = 'e53c942c7ba4d755827e0feabdcc143e33f6f06ef30b448951ff3f5955d71225'


def control_bytes(parameters):
    """One-mip DX10 RGBA8 8x4; alpha stores color-space-independent parameters."""
    pixels = bytearray(8*4*4)
    pixels[:8] = SIGNATURE
    values = [*parameters['shade'], parameters['toony'], (parameters['shift']+1)/2,
              parameters['gi_equalization']]
    if any(not 0 <= v <= 1 for v in values):
        raise ValueError('Invalid toon parameter range')
    for index, value in enumerate(values, 2):
        pixels[index*4+3] = round(value*255)
    header = bytearray(148)
    header[:4] = b'DDS '
    struct.pack_into('<7I', header, 4, 124, 0x100F, 4, 8, 8*4, 0, 1)
    struct.pack_into('<II4s', header, 76, 32, 4, b'DX10')
    struct.pack_into('<I', header, 108, 0x1000)
    struct.pack_into('<5I', header, 128, 28, 3, 0, 1, 0)
    return bytes(header+pixels)


def parameters_for(material, strength=.15):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    # A calm prototype palette. Original shade multipliers tint this palette;
    # source shade textures, matcaps, outlines and rim effects are not ported.
    shade = mtoon.get('shadeColorFactor', [.75, .77, .85])
    lit = material.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])
    return {'shade': [max(0., min(1., shade[i]/lit[i]))*(1-strength) if lit[i] > 1e-6 else 1-strength
                      for i in range(3)],
            'toony': max(0., min(.98, mtoon.get('shadingToonyFactor', .9))),
            'shift': max(-1., min(1., mtoon.get('shadingShiftFactor', 0.))),
            'gi_equalization': max(0., min(1., mtoon.get('giEqualizationFactor', .9)))}


def patch_lighting(source, diagnostic=False):
    if hashlib.sha256(source).hexdigest() != SUPPORTED_LIGHTING:
        raise ValueError('Unsupported Community Shaders Lighting.hlsl; generate an explicitly verified adapter first')
    text = source.decode('utf-8-sig').replace('\r\n', '\n')
    include = '#\tinclude "Common/LightingEval.hlsli"'
    replacement = '''#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)
#define EvaluateLighting V2SOriginalEvaluateLighting
#endif
'''+include+'''
#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)
#undef EvaluateLighting
#define V2S_TOON_DIAGNOSTIC '''+str(int(diagnostic))+'''
#include "VRM2Skyrim/ToonBridge.hlsli"
#endif'''
    initializer = '\tPS_OUTPUT psout;'
    ambient = '\tfloat4 color = 0;'
    forward = '#\tif !defined(DEFERRED)\n\tcolor.xyz = Color::IrradianceToLinear(color.xyz);'
    finish = '\treturn psout;'
    for token in (include, initializer, ambient, forward, finish):
        if text.count(token) != 1:
            raise ValueError('Shader integration anchor changed: '+token)
    text = text.replace(include, replacement)
    text = text.replace(initializer, initializer+'''
#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)
    V2SInitializeToon();
#endif''')
    text = text.replace(ambient, '''#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)
    float3 v2sAmbient = 0;
    if (V2SToonEnabled) {
        float3 flatAmbient = float3(DirectionalAmbient[0].w, DirectionalAmbient[1].w, DirectionalAmbient[2].w);
        v2sAmbient = V2SToonAmbient(directionalAmbientColor, Color::Ambient(flatAmbient), V2SToon.giEqualization);
    }
#endif
'''+ambient)
    # Resolve after all lights/skylighting, before forward fog and deferred
    # output. Clear deferred reflection/GI inputs as well as local specular.
    text = text.replace(forward, '''#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)
    if (V2SToonEnabled) {
        color.xyz = saturate(material.BaseColor) * V2SToonResolve(
            V2SToonDirectSum, V2SToonUnshadedSum, v2sAmbient, V2SToon.shade);
        specularColor = 0;
        indirectLobeWeights.specular = 0;
        indirectLobeWeights.diffuse = 0;
        outputAlbedo = 0;
        directionalAmbientColor = 0;
        material.Roughness = 1;
#if defined(WETNESS_EFFECTS)
        wetnessReflectance = 0;
        waterRoughnessSpecular = 1;
#endif
    }
#endif
'''+forward)
    text = text.replace(finish, '''#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR) && V2S_TOON_DIAGNOSTIC
    if (V2SToonEnabled)
        psout.Diffuse.xyz = float3(1, 0, 1);
#endif
'''+finish)
    # A reserved non-SSS mask value carries ownership into the later CS
    # composite pass. Ordinary masks use y=0/1; x=z=0 excludes normal skin.
    masks = '\t// Stored as 1 - vertexAO so the cleared default (0) means no occlusion'
    if text.count(masks) != 1:
        raise ValueError('Shader deferred marker anchor changed')
    text = text.replace(masks, '''#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)
    if (V2SToonEnabled)
        psout.Masks.xyz = float3(0, 0.5, 0);
#endif

'''+masks)
    return text.encode('utf8')


def patch_composite(source):
    if hashlib.sha256(source).hexdigest() != SUPPORTED_COMPOSITE:
        raise ValueError('Unsupported Community Shaders DeferredCompositeCS.hlsl')
    text = source.decode('utf-8-sig').replace('\r\n', '\n')
    include = '#include "Common/GBuffer.hlsli"'
    albedo = '\tfloat3 albedo = AlbedoTexture[dispatchID.xy];'
    sample = '\tSampleSSGI(dispatchID.xy, normalWS, ssgiAo, ssgiIl);'
    for token in (include, albedo, sample):
        if text.count(token) != 1:
            raise ValueError('Shader composite anchor changed: '+token)
    text = text.replace(include, include+'\n#include "VRM2Skyrim/ToonDeferred.hlsli"')
    text = text.replace(albedo, albedo+'\n\tconst bool v2sMarked = V2SIsMarkedMask(MasksTexture[dispatchID.xy]);')
    text = text.replace(sample, sample+'''
    if (v2sMarked) {
        ssgiAo = 1;
        ssgiIl = 0;
    }''')
    return text.encode('utf8')


def shader_package(shader_root, output, diagnostic=False):
    shader_root, output = Path(shader_root), Path(output)
    source = shader_root/'Lighting.hlsl'
    patched = patch_lighting(source.read_bytes(), diagnostic)
    composite = patch_composite((shader_root/'DeferredCompositeCS.hlsl').read_bytes())
    folder = 'shader-diagnostic-mod' if diagnostic else 'shader-mod'
    target = output/folder/'Shaders'
    (target/'VRM2Skyrim').mkdir(parents=True, exist_ok=True)
    (target/'Lighting.hlsl').write_bytes(patched)
    (target/'DeferredCompositeCS.hlsl').write_bytes(composite)
    for path in (ROOT/'runtime/toon').glob('*.hlsli'):
        shutil.copy2(path, target/'VRM2Skyrim'/path.name)
    shutil.copy2(shader_root/'LICENSE', target/'VRM2Skyrim/CommunityShaders-LICENSE.txt')
    shutil.copy2(ROOT/'docs/TOON.md', target/'VRM2Skyrim/README.md')
    shutil.copy2(ROOT/'LICENSE', target/'VRM2Skyrim/VRM2Skyrim-LICENSE.txt')
    metadata = {'prototype': 3, 'diagnostic': diagnostic, 'community_shaders_dll_version': '1.9.0.0',
                'lighting_sha256': SUPPORTED_LIGHTING,
                'patched_lighting_sha256': hashlib.sha256(patched).hexdigest(),
                'composite_sha256': SUPPORTED_COMPOSITE,
                'patched_composite_sha256': hashlib.sha256(composite).hexdigest(),
                'scope': 'non-landscape non-PBR Glowmap material with exact 8x4 DDS signature',
                'original_evaluation_for_unmarked_materials': True}
    (target/'VRM2Skyrim/adapter.json').write_text(json.dumps(metadata, indent=2), encoding='utf8')
    suffix = '-Diagnostic' if diagnostic else ''
    archive = output/f'VRM2Skyrim-Toon-Shader-Prototype-3{suffix}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for path in sorted((output/folder).rglob('*')):
            if path.is_file():
                package.write(path, path.relative_to(output/folder).as_posix())
    logging.info('Toon shader prototype: %s; original shader SHA256 %s', archive, SUPPORTED_LIGHTING)
    return archive


def avatar_paths(output, settings, manifest):
    mesh_dir = output/'mod/meshes'/settings.asset_dir
    return {mesh_dir/c['file'] for c in manifest['components']} | set(mesh_dir.glob('fixed_*.nif'))


def prepare_materials(output, strength=.15):
    """Mark only source avatar shapes, leaving collisions and existing gear alone."""
    from custom_skeleton import NifFile
    output = Path(output)
    settings = load_settings(output)
    settings.toon_enabled = True
    settings.save(output/'settings.json')
    manifest = json.loads((output/'appearance.json').read_text(encoding='utf8'))
    originals = {}
    if (output/'source.glb').exists():
        from inspect_vrm import read_glb
        from nif_materials import normalize_material_colors
        document, _ = read_glb(output/'source.glb')
        normalize_material_colors(document)
        originals = {m['name']: m for m in document.get('materials', [])}
    mod = output/'mod'
    prepared = []
    shapes = {s['name']: s for c in manifest['components'] for s in c.get('shapes', [])}
    by_file = {c['file']: {s['name']: s for s in c.get('shapes', [])} for c in manifest['components']}
    paths = avatar_paths(output, settings, manifest)
    for path in sorted(paths):
        with NifFile(str(path.resolve())) as nif:
            infos = []
            for shape in nif.shapes:
                if shape.name.startswith('V2SCollision_'):
                    continue
                info = by_file.get(path.name, shapes).get(shape.name)
                if info is None:
                    raise ValueError('Unregistered source material in toon appearance: '+shape.name)
                infos.append({**info, 'name': shape.name})
        for info in infos:
            material = info.get('material_policy')
            if material is None:
                raise ValueError('Regenerate the appearance to retain source material metadata')
            material = originals.get(material.get('name'), material)
            parameters = parameters_for(material, strength)
            data = control_bytes(parameters)
            digest = hashlib.sha256(data).hexdigest()[:16]
            relative = f'textures/{settings.asset_dir}/toon_{digest}.dds'
            texture = mod/relative
            texture.parent.mkdir(parents=True, exist_ok=True)
            texture.write_bytes(data)
            validate_dds(texture, (8, 4), 'R8G8B8A8_UNORM')
            with NifFile(str(path.resolve())) as nif:
                shape = next(s for s in nif.shapes if s.name == info['name'])
                properties = shape.shader.properties
                properties.Shader_Type = 2  # BSLSPShaderType.Glow_Shader
                properties.Shader_Flags_1 |= 1 << 22  # OWN_EMIT
                properties.Shader_Flags_2 |= 1 << 6   # GLOW_MAP
                properties.Emissive_Color[:] = (0., 0., 0., 1.)
                properties.Emissive_Mult = 0.
                shape.shader.write_properties()
                shape.set_texture('Glow', relative.replace('/', '\\'))
                nif.save()
            with NifFile(str(path.resolve())) as nif:
                shape = next(s for s in nif.shapes if s.name == info['name'])
                if shape.shader.properties.Shader_Type != 2 or shape.shader.textures.get('Glow', '').replace('\\', '/') != relative:
                    raise ValueError('Toon marker did not survive NIF export: '+info['name'])
                if shape.shader.properties.Emissive_Mult != 0:
                    raise ValueError('Toon marker must not illuminate the fallback material')
            prepared.append({'file': path.name, 'shape': info['name'], 'control': relative,
                             'parameters': parameters})
    report = {'prototype': 1, 'enabled': True, 'materials': prepared, 'game_verified': False}
    (output/'toon.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    validate_toon(output)
    logging.info('Toon prototype: %d source shapes; zero emission, original alpha/skin retained', len(prepared))
    return report


def validate_toon(output):
    from custom_skeleton import NifFile
    output = Path(output)
    settings = load_settings(output)
    manifest = json.loads((output/'appearance.json').read_text(encoding='utf8'))
    report = json.loads((output/'toon.json').read_text(encoding='utf8'))
    if not settings.toon_enabled or not report['enabled'] or not report['materials']:
        raise ValueError('Toon material report disagrees with settings')
    seen = set()
    for entry in report['materials']:
        key = (entry['file'], entry['shape'])
        if key in seen:
            raise ValueError('Duplicate toon material declaration')
        seen.add(key)
        path = output/'mod/meshes'/settings.asset_dir/entry['file']
        relative = entry['control']
        if not relative.startswith('textures/'+settings.asset_dir+'/toon_') or '..' in relative:
            raise ValueError('Toon control is not private to this follower')
        data = (output/'mod'/relative).read_bytes()
        if data != control_bytes(entry['parameters']):
            raise ValueError('Toon DDS parameters changed: '+entry['shape'])
        validate_dds(output/'mod'/relative, (8, 4), 'R8G8B8A8_UNORM')
        with NifFile(str(path.resolve())) as nif:
            shape = next(s for s in nif.shapes if s.name == entry['shape'])
            p = shape.shader.properties
            if (p.Shader_Type != 2 or not p.Shader_Flags_1 & (1 << 22)
                    or not p.Shader_Flags_2 & (1 << 6) or p.Emissive_Mult != 0
                    or any(p.Emissive_Color[i] != 0 for i in range(3))
                    or shape.shader.textures.get('Glow', '').replace('\\', '/') != relative):
                raise ValueError('Invalid native toon material marker: '+entry['shape'])
    expected = set()
    for path in avatar_paths(output, settings, manifest):
        with NifFile(str(path.resolve())) as nif:
            expected.update((path.name, s.name) for s in nif.shapes if not s.name.startswith('V2SCollision_'))
    if seen != expected:
        raise ValueError(f'Toon material coverage differs from avatar: missing={sorted(expected-seen)}, '
                         f'unexpected={sorted(seen-expected)}')
    logging.info('Validated %d zero-emission native toon materials and private DDS controls', len(seen))
    return len(seen)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--shader-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true', help='mark recognized surfaces magenta for activation checks')
    args = parser.parse_args()
    if args.shader_root:
        shader_package(args.shader_root, args.output, args.diagnostic)
    else:
        prepare_materials(args.output)
