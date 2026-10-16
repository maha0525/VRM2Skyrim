"""Production source-domain UV mapping versus native GPU sampler addressing."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toon import control_bytes, parameters_for  # noqa: E402
from toon_shade import WRAP_CODES, build_shade, pack_shade, shade_image  # noqa: E402
from toon_gpu_fixture import build  # noqa: E402


def rgba_dds(path, image):
    header = bytearray(control_bytes(parameters_for({}))[:148])
    struct.pack_into('<III', header, 12, image.height, image.width, image.width*4)
    path.write_bytes(header+image.tobytes())


def verify(output):
    output.mkdir(parents=True, exist_ok=True)
    build(output, ROOT/'tests/toon_uv_gpu.cpp')
    bridge = (ROOT/'runtime/toon/ToonBridge.hlsli').read_text(encoding='utf8')
    code = bridge[bridge.index('        float2 shadeUv ='):bridge.index('        float3 shadeSurface =')]
    cases = [(7, 5, u, v) for u in WRAP_CODES for v in WRAP_CODES]
    cases += [(2, 2, 33071, 10497), (1254, 1254, 33071, 33071), (64, 8, 10497, 10497)]
    results = []
    for width, height, u, v in cases:
        folder = output/f'{width}x{height}-{u}-{v}'
        folder.mkdir(exist_ok=True)
        y, x = np.mgrid[:height, :width]
        pixels = np.stack((x/max(1, width-1)*220, y/max(1, height-1)*220,
                           (x+y)/max(1, width+height-2)*180, np.full_like(x, 255)), axis=2).astype(np.uint8)
        image = Image.fromarray(pixels)
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        binary = stream.getvalue()
        document = {'bufferViews': [{'byteLength': len(binary)}], 'images': [{'bufferView': 0}],
                    'textures': [{'source': 0, 'sampler': 0}], 'samplers': [{'wrapS': u, 'wrapT': v}]}
        material = {'extensions': {'VRMC_materials_mtoon': {
            'shadeColorFactor': [1, 1, 1], 'shadeMultiplyTexture': {'index': 0}}}}
        parameters = parameters_for(material, authored=True)
        image, _ = shade_image(document, binary, material)
        packed = pack_shade(image, parameters)
        data, report = build_shade(folder, document, binary, material, parameters)
        rgba_dds(folder/'source.dds', image)
        rgba_dds(folder/'packed.dds', packed)
        (folder/'encoded.dds').write_bytes(data)
        kernel = ('Texture2D<float4> Original:register(t0); Texture2D<float4> Packed:register(t1);\n'
                  'SamplerState SourceSampler:register(s0); SamplerState PackedSampler:register(s1);\n'
                  'RWTexture2D<float4> Result:register(u0);\n'
                  '[numthreads(8,8,1)] void main(uint3 id:SV_DispatchThreadID){if(any(id.xy>=257))return;\n'
                  'float2 uv=float2(id.xy)/64.0-1.5; float2 uv_ddx=0,uv_ddy=0;\n'
                  f'float2 size=float2({packed.width},{packed.height}); bool V2SToonSourceDomain=true;\n'
                  f'uint2 V2SToonSourceSize=uint2({width},{height}),V2SToonWrap=uint2({WRAP_CODES[u]},{WRAP_CODES[v]});\n'
                  +code+'\nResult[id.xy]=abs(Packed.SampleLevel(PackedSampler,shadeUv,0)-Original.SampleLevel(SourceSampler,uv,0));}\n')
        (folder/'kernel.hlsl').write_text(kernel, encoding='utf8')
        # Different normalized texture sizes incur sub-texel GPU sampling
        # precision error; allow less than 1/16 of an 8-bit colour step.
        exact_tolerance = 1/4096
        encoded_tolerance = .045 if report['format'] == 'BC7_UNORM' else exact_tolerance
        for name, tolerance in [('packed.dds', exact_tolerance), ('encoded.dds', encoded_tolerance)]:
            args = [str(output/'toon_gpu.exe'), str(folder/'kernel.hlsl'), str(folder/'source.dds'),
                    str(folder/name), str(u), str(v), str(tolerance)]
            run = subprocess.run(args, capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError(str(folder)+' '+name+'\n'+run.stdout+run.stderr)
            results.append({'size': [width, height], 'wrap': [u, v], 'texture': name,
                            'maximum_allowed_error': tolerance, 'output': run.stdout.strip(),
                            'metadata_size': report['source_size']})
    (output/'uv-verification.json').write_text(json.dumps(results, indent=2), encoding='utf8')
    print('Native GPU source UV/addressing comparisons passed:', len(results))


if __name__ == '__main__':
    verify(Path(sys.argv[1]).resolve())
