"""Production atlas sampling, float controls, derivatives and effect equations."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toon import parameters_for  # noqa: E402
from toon_effects import build_material  # noqa: E402
from test_toon_effects import embedded  # noqa: E402
from toon_gpu_fixture import build  # noqa: E402
from toon_uv_gpu import rgba_dds  # noqa: E402


def verify(output):
    output.mkdir(parents=True, exist_ok=True)
    build(output, ROOT/'tests/toon_effects_gpu.cpp')
    effects_code = (ROOT/'runtime/toon/ToonEffects.hlsli').read_text(encoding='utf8')
    prefix = '''Texture2D<float4> Original:register(t0); Texture2D<float4> TexGlowSampler:register(t6);
SamplerState SourceSampler:register(s0); SamplerState SampGlowSampler:register(s6);
static bool V2SToonEnabled=true;static uint2 V2SToonTextureSize;
static float3 V2SToonUnshadedSum=0;
float V2SToonData(uint i){return TexGlowSampler.Load(int3(i*4,V2SToonTextureSize.y-4,0)).a;}
namespace Color {
float3 Diffuse(float3 v){return v;}
float3 LinearToSrgb(float3 v){return v;}
float3 SrgbToLinear(float3 v){return v;}
}
'''
    results = []

    def run(name, atlas, source, body, tolerance):
        folder = output/name
        folder.mkdir(exist_ok=True)
        (folder/'atlas.dds').write_bytes(atlas)
        rgba_dds(folder/'source.dds', source)
        code = prefix+effects_code+'''\nfloat4 main(float4 position:SV_POSITION):SV_Target0 {
uint w,h;TexGlowSampler.GetDimensions(w,h);V2SToonTextureSize=uint2(w,h);
if(!V2SInitializeEffects()) return float4(10,10,10,1);V2SToonEffects=true;
float2 coord=position.xy/256.;
'''+body+'\n}\n'
        (folder/'kernel.hlsl').write_text(code, encoding='utf8')
        process = subprocess.run([str(output/'toon_gpu.exe'), str(folder/'kernel.hlsl'),
            str(folder/'source.dds'), str(folder/'atlas.dds'), str(tolerance)], capture_output=True, text=True)
        if process.returncode:
            raise RuntimeError(name+'\n'+process.stdout+process.stderr)
        results.append({'case': name, 'tolerance': tolerance, 'result': process.stdout.strip()})

    # All maps occupy different rectangles; compare their native address modes.
    for size in [(7, 5), (64, 8), (1254, 1254)]:
        w, h = size
        y, x = np.mgrid[:h, :w]
        pixels = np.stack((x/max(1,w-1)*200+20, y/max(1,h-1)*180+20,
            (x+y)/max(1,w+h-2)*150+20, np.full_like(x,255)), axis=-1).astype(np.uint8)
        source = Image.fromarray(pixels)
        for u, v in [(10497,10497), (33071,33071), (33648,33648), (33071,33648)]:
            doc, binary = embedded([source]*4, [[u,v]]*4)
            m = {'normalTexture': {'index': 3, 'scale': -.125}, 'extensions': {'VRMC_materials_mtoon': {
                'shadeMultiplyTexture': {'index': 0}, 'shadeColorFactor': [1]*3,
                'matcapTexture': {'index': 1}, 'matcapFactor': [1]*3, 'rimMultiplyTexture': {'index': 2},
                'parametricRimLiftFactor': -.35, 'parametricRimFresnelPowerFactor': 12.375}}}
            atlas, report = build_material(output, doc, binary, m, parameters_for(m, authored=True))
            address = 'float2 uv=coord*4-1.5;'
            address += ('float2 nativeUv=float2('+('saturate(uv.x)' if u==33071 else '1-abs(frac(uv.x*.5)*2-1)' if u==33648 else 'frac(uv.x)')
                +','+('saturate(uv.y)' if v==33071 else '1-abs(frac(uv.y*.5)*2-1)' if v==33648 else 'frac(uv.y)')+');')
            # Native sampler clamps explicitly addressed texel coordinates into a tiled 3x3 source.
            # Use direct Load/bilinear reference so clamp endpoints never wrap again.
            reference = f'''float2 px=nativeUv*float2({w},{h})-.5;int2 p=int2(floor(px));float2 f=frac(px);
float3 taps[4];[unroll]for(int k=0;k<4;k++){{int2 q=p+int2(k%2,k/2);
'''
            for axis, mode, count in [('x',u,w),('y',v,h)]:
                if mode==33071:
                    reference += f'q.{axis}=clamp(q.{axis},0,{count-1});'
                elif mode==33648:
                    reference += f'q.{axis}=((q.{axis}%{2*count})+{2*count})%{2*count};q.{axis}=q.{axis}<{count}?q.{axis}:{2*count-1}-q.{axis};'
                else:
                    reference += f'q.{axis}=((q.{axis}%{count})+{count})%{count};'
            reference += '''taps[k]=Original.Load(int3(q,0)).rgb;}
float3 expected=lerp(lerp(taps[0],taps[1],f.x),lerp(taps[2],taps[3],f.x),f.y);
float3 error=0;[unroll]for(uint i=0;i<4;i++)error=max(error,abs(V2SSampleEffect(i,uv)-expected));
if(V2SToonNormalScale!=-.125||V2SToonRimPower!=12.375||abs(V2SToonRimLift+.35)>1e-7)error=10;
return float4(error,1);'''
            run(f'sample-{w}-{h}-{u}-{v}', atlas, source, address+reference,
                .045 if report['format']=='BC7_UNORM' else 1/4096)

    normal = Image.new('RGBA', (7,5), (179,204,240,255))
    doc, binary = embedded([normal])
    for scale in [0., .5, 1., -.25]:
        m = {'normalTexture': {'index':0,'scale':scale}, 'extensions': {'VRMC_materials_mtoon': {'shadeColorFactor':[1]*3}}}
        atlas, _ = build_material(output, doc, binary, m, parameters_for(m, authored=True))
        for name, uv, tangent, bitangent in [
            ('standard','coord','float3(1,0,0)','float3(0,1,0)'),
            ('mirrored','float2(-coord.x,coord.y)','float3(-1,0,0)','float3(0,1,0)'),
            ('rotated','float2(coord.y,-coord.x)','float3(0,1,0)','float3(-1,0,0)'),
            ('degenerate','float2(0,0)','float3(0,0,0)','float3(0,0,0)')]:
            body = f'''float2 uv={uv};float3 n=float3(0,0,1);
float3 actual=V2SApplySourceNormal(n,float3(coord,0),uv);
float3 ts=Original.SampleLevel(SourceSampler,uv,0).rgb*2-1;ts.xy*={scale};ts=normalize(ts);
float3 expected=normalize({tangent}*ts.x+{bitangent}*ts.y+n*ts.z);
'''
            if name=='degenerate':
                body += 'expected=n;'
            body += 'return float4(abs(actual-expected),1);'
            run(f'normal-{name}-{scale}', atlas, normal, body, 1e-5)
    # Separate analytical Fresnel and lighting-mix endpoints, including emission at mix=0.
    for mix in [0., .35, 1.]:
        m = {'extensions': {'VRMC_materials_mtoon': {'shadeColorFactor':[1]*3,
            'parametricRimColorFactor':[.2,.1,.3], 'parametricRimFresnelPowerFactor':2.5,
            'parametricRimLiftFactor':-.15, 'rimLightingMixFactor':mix}}}
        atlas, _ = build_material(output, {}, b'', m, parameters_for(m, authored=True))
        body = f'''float3 n=normalize(float3(coord.x*2-1,1,coord.y*2-1)),v=float3(0,1,0);
float3 actual=V2SFinishEffects(float3(.1,.1,.1),n,v,coord,0,0);
float3 expected=.1+float3(.2,.1,.3)*pow(saturate(1-n.y-.15),2.5)*(1-{mix});
return float4(abs(actual-expected),1);'''
        run(f'rim-mix-{mix}', atlas, normal, body, 1e-5)
    matcap = Image.fromarray(np.stack(np.meshgrid(np.arange(64)*3, np.arange(64)*3)
        +[np.full((64,64),32),np.full((64,64),255)],axis=-1).astype(np.uint8))
    doc, binary = embedded([matcap])
    m = {'extensions': {'VRMC_materials_mtoon': {'shadeColorFactor':[1]*3,
        'matcapTexture':{'index':0},'matcapFactor':[1]*3,'rimLightingMixFactor':0}}}
    atlas, _ = build_material(output, doc, binary, m, parameters_for(m, authored=True))
    for name, view, expected_uv in [('forward','float3(0,1,0)','float2(n.x,n.z)*.495+.5'),
                                    ('pole','float3(0,0,1)','float2(-n.x,n.y)*.495+.5')]:
        body = f'''float3 n=normalize(float3(coord.x*2-1,1,coord.y*2-1));
float3 actual=V2SFinishEffects(0,n,{view},coord,0,0);
float3 expected=Original.SampleLevel(SourceSampler,{expected_uv},0).rgb;
return float4(abs(actual-expected),1);'''
        run('matcap-'+name,atlas,matcap,body,.025)
    (output/'effect-verification.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print('Native pixel effect reference cases passed:',len(results))


if __name__=='__main__':
    verify(Path(sys.argv[1]).resolve())
