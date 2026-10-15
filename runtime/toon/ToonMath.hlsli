// VRM2Skyrim experimental toon lighting. MIT license; see repository LICENSE.
#ifndef VRM2SKYRIM_TOON_MATH
#define VRM2SKYRIM_TOON_MATH
struct V2SToonParameters
{
    float3 shade;
    float toony;
    float shift;
    float giEqualization;
};

float3 V2SToonDirect(float3 normal, float3 lightDirection, float3 radiance,
                     float shadow, V2SToonParameters parameters)
{
    float ndotl = dot(normal, lightDirection);
    // A shadow moves the sample into the shade band, rather than painting black.
    float lighting = lerp(-1.0, ndotl, saturate(shadow)) + parameters.shift;
    float width = max(0.02, 1.0 - parameters.toony);
    float lit = saturate((lighting + width) / (2.0 * width));
    return max(radiance, 0.0) * lerp(parameters.shade, 1.0.xxx, lit);
}

float3 V2SToonAmbient(float3 directional, float3 nondirectional, float equalization)
{
    return lerp(max(directional, 0.0), max(nondirectional, 0.0), saturate(equalization));
}
#endif
