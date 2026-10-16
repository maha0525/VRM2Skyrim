// Reserved non-SSS GBuffer marker, written only after the private DDS check.
// Native Lighting masks use y=0/1. R11G11B10_FLOAT can round blended 0.5
// down one representable step (0.49609375); also allow an RGBA8 fixture.
bool V2SIsMarkedMask(float3 mask)
{
    return mask.x == 0 && abs(mask.y - 0.5) < 0.0041 && mask.z == 0;
}
