# Preserve source material face culling

The user observed thick dark strips in a private avatar's sclera after a
successful wardrobe/armor test. The original VRM face materials have
doubleSided=false, default morphs are zero, and the face texture includes white
sclera. The converter forced DOUBLE_SIDED on every material. Source-eye renders
with identical geometry/texture and only culling changed reproduce the strip.
Ray casts identify the first surface as a back-facing eyelash triangle, followed
by the front-facing eye. This is a converter fault, not required VRM preparation.

Preserve doubleSided (default false) independently of alphaMode and MToon depth
write. Respect explicit double-sided materials. Correct all original-appearance
export modes and validate the native NIF readback at export. Preserve vertices,
normals, weights, UVs, textures, expression defaults and wardrobe runtime.

Cycles does not reliably implement raster backface culling from the material
viewport setting. The output-NIF and source preview must use an explicit
Geometry.Backfacing transparent branch only for single-sided materials, so the
preview cannot hide or reproduce a different contract from the output. Keep
native armor material settings intact; changes are per original VRM material.

Verify opaque, masked and blended materials, explicit false/true and omitted
doubleSided, repeated application and actual native NIF flags. Retain same-camera
source A/B and surface-identification evidence locally, keeping private avatar
assets and generated MODs out of the repository.
