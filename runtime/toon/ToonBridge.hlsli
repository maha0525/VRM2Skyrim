// Included only in non-landscape non-PBR Lighting pixel shaders, after LightingEval.
#include "VRM2Skyrim/ToonMath.hlsli"
static bool V2SToonEnabled = false;
static V2SToonParameters V2SToon;
static float3 V2SToonDirectSum = 0;
static float3 V2SToonUnshadedSum = 0;
static bool V2SToonAuthored = false;
static uint2 V2SToonTextureSize = 0;
static bool V2SToonSourceDomain = false;
static uint2 V2SToonSourceSize = 0;
static uint2 V2SToonWrap = 0;

float V2SToonData(uint index)
{
    // Alpha is linear in both UNORM and sRGB SRVs. Never encode data in RGB.
    uint2 pixel = V2SToonAuthored ? uint2(index * 4, V2SToonTextureSize.y - 4) : uint2(index % 8, index / 8);
    return TexGlowSampler.Load(int3(pixel, 0)).a;
}

void V2SInitializeToon()
{
    V2SToonEnabled = false;
    V2SToonAuthored = false;
    V2SToonSourceDomain = false;
    V2SToonDirectSum = 0;
    V2SToonUnshadedSum = 0;
    uint shaderTechnique = (Permutation::PixelShaderDescriptor >> 24) & 0x3F;
    if (shaderTechnique != Permutation::LightingTechnique::Glowmap)
        return;
    uint width, height;
    TexGlowSampler.GetDimensions(width, height);
    V2SToonTextureSize = uint2(width, height);
    bool legacy = width == 8 && height == 4;
    V2SToonAuthored = width >= 64 && height >= 16 && width % 4 == 0 && height % 4 == 0;
    if (!legacy && !V2SToonAuthored) return;
    uint headerY = V2SToonAuthored ? height - 4 : 0;
    float4 header0 = TexGlowSampler.Load(int3(0, headerY, 0));
    float4 header1 = TexGlowSampler.Load(int3(V2SToonAuthored ? 4 : 1, headerY, 0));
    if (any(abs(header0 - float4(1, 0, 1, 1)) > 0.001) ||
        any(abs(header1 - float4(0, 1, 0, 1)) > 0.001))
        return;
    if (V2SToonAuthored) {
        uint version = (uint)round(V2SToonData(8) * 255.0);
        V2SToonSourceDomain = version == 128;
        if (version != 255 && !V2SToonSourceDomain) return;
        if (V2SToonSourceDomain) {
            V2SToonSourceSize = uint2(round(V2SToonData(9)*255.0) + round(V2SToonData(10)*255.0)*256.0,
                                      round(V2SToonData(11)*255.0) + round(V2SToonData(12)*255.0)*256.0);
            V2SToonWrap = uint2(round(V2SToonData(13)*255.0), round(V2SToonData(14)*255.0));
            if (any(V2SToonSourceSize == 0) || V2SToonSourceSize.x + 8 > width || V2SToonSourceSize.y + 12 > height) return;
            if (any((V2SToonWrap != 0) && (V2SToonWrap != 128) && (V2SToonWrap != 255))) return;
        }
    }
    V2SToon.shade = V2SToonShade(float3(V2SToonData(2), V2SToonData(3), V2SToonData(4)));
    V2SToon.toony = V2SToonData(5);
    V2SToon.shift = V2SToonData(6) * 2.0 - 1.0;
    V2SToon.giEqualization = V2SToonData(7);
    V2SToonEnabled = true;
}

void EvaluateLighting(DirectContext context, MaterialProperties material, float3x3 tbnTr,
                      float2 uv, float2 uv_ddx, float2 uv_ddy,
                      out DirectLightingOutput lightingOutput)
{
    if (!V2SToonEnabled) {
        V2SOriginalEvaluateLighting(context, material, tbnTr, uv, uv_ddx, uv_ddy, lightingOutput);
        return;
    }
    lightingOutput = (DirectLightingOutput)0;
    if (V2SToonAuthored) {
        float2 size = float2(V2SToonTextureSize);
        float2 shadeUv = frac(uv);
        float2 scale = float2(1.0, (size.y - 12.0) / size.y);
        if (V2SToonSourceDomain) {
            shadeUv = float2(V2SToonWrap.x == 128 ? saturate(uv.x) : V2SToonWrap.x == 255 ? 1-abs(frac(uv.x*.5)*2-1) : frac(uv.x),
                             V2SToonWrap.y == 128 ? saturate(uv.y) : V2SToonWrap.y == 255 ? 1-abs(frac(uv.y*.5)*2-1) : frac(uv.y));
            scale = float2(V2SToonSourceSize) / size;
        }
        shadeUv *= scale;
        // Repeat gutters preserve bilinear UV seams without sampling metadata.
        shadeUv.y += 4.0 / size.y;
        if (V2SToonSourceDomain) shadeUv.x += 4.0 / size.x;
        float3 shadeSurface = Color::Diffuse(TexGlowSampler.SampleGrad(SampGlowSampler,
            shadeUv, uv_ddx * scale, uv_ddy * scale).rgb);
        float width = max(0.0001, 1.0 - V2SToon.toony);
        float band = saturate((dot(context.worldNormal, context.lightDir) + V2SToon.shift + width) / (2.0 * width));
        band *= saturate(min(context.detailedShadow, context.softShadow));
        lightingOutput.diffuse = lerp(shadeSurface, saturate(material.BaseColor), band) * max(context.lightColor, 0.0);
    } else {
        lightingOutput.diffuse = V2SToonDirect(context.worldNormal, context.lightDir,
            context.lightColor, min(context.detailedShadow, context.softShadow), V2SToon);
    }
    lightingOutput.diffuse *= Color::VanillaNormalization();
    V2SToonDirectSum += lightingOutput.diffuse;
    V2SToonUnshadedSum += max(context.lightColor, 0.0) * Color::VanillaNormalization();
}
