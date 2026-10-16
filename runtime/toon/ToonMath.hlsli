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
float3 V2SToonShade(float3 source)
{
    // Preserve authored dark shades and hue; pale shades need enough contrast
    // to remain visible after Skyrim's ambient light is added.
    float peak = max(source.r, max(source.g, source.b));
    return source * min(1.0, 0.55 / max(peak, 0.0001));
}

float3 V2SToonResolve(float3 direct, float3 unshaded, float3 ambient, float3 shade)
{
    ambient = max(ambient, 0.0) * 0.6;
    float3 available = max(unshaded, 0.0) + ambient;
    // Both bands use the same exposure, independent of the shaded pixel.
    float exposure = rcp(max(1.0, max(available.r, max(available.g, available.b))));
    return (max(direct, 0.0) + ambient * shade) * exposure;
}
#endif
