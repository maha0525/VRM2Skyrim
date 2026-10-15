// Included only in skinned non-PBR Lighting pixel shaders, after LightingEval.
#include "VRM2Skyrim/ToonMath.hlsli"
static bool V2SToonEnabled = false;
static V2SToonParameters V2SToon;

float V2SToonData(uint index)
{
    // Alpha is linear in both UNORM and sRGB SRVs. Never encode data in RGB.
    return TexGlowSampler.Load(int3(index % 8, index / 8, 0)).a;
}

void V2SInitializeToon()
{
    V2SToonEnabled = false;
    uint shaderTechnique = (Permutation::PixelShaderDescriptor >> 24) & 0x3F;
    if (shaderTechnique != Permutation::LightingTechnique::Glowmap)
        return;
    uint width, height;
    TexGlowSampler.GetDimensions(width, height);
    if (width != 8 || height != 4)
        return;
    float4 header0 = TexGlowSampler.Load(int3(0, 0, 0));
    float4 header1 = TexGlowSampler.Load(int3(1, 0, 0));
    if (any(abs(header0 - float4(1, 0, 1, 1)) > 0.001) ||
        any(abs(header1 - float4(0, 1, 0, 1)) > 0.001))
        return;
    V2SToon.shade = float3(V2SToonData(2), V2SToonData(3), V2SToonData(4));
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
    lightingOutput.diffuse = V2SToonDirect(context.worldNormal, context.lightDir,
        context.lightColor, min(context.detailedShadow, context.softShadow), V2SToon)
        * Color::VanillaNormalization();
}
