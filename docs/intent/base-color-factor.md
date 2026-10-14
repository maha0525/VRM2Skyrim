# Preserve original material base color factors

The supplied Cecil VRM uses a textured eye layer with baseColorFactor RGB=(0,0,0)
and alpha=.375. The exported NIF retains alpha=.375 but points to the original
white RGB texture. PyNifly finds the texture behind Blender's color multiply and
does not export that RGB multiplier. Other original materials lose their tint
through the same path, including hair ribbons and eyelash/iris layers.

The user's Unity reference also exposed an incorrect source-preview baseline.
VRM0 MToon _Color is sRGB, whereas fallback glTF baseColorFactor is interpreted
as linear. Follow official UniVRM MigrationMToonMaterial: read the authoritative
legacy _Color and convert RGB to linear before Blender import and baking. Alpha
stays unchanged; do not gamma-convert VRM1 or non-MToon glTF materials. Normalize
both source previews and conversion through the same idempotent helper.

The remaining pale eyelash overlay is UeMatugeB (queue 3000), covering UeMatuge
(queue 4000) in depth-based renders. Preserve explicit source queue ordering in
native NIF root children and NiAlphaProperty No Sorter, only when multiple alpha
queues exist. Keep opaque depth testing and writing. Reuse for head variants.
Cycles cannot honor raster queues by tracing geometric depth. Preview such models
as queue passes with opaque/cutout holdouts and linear alpha-over composition.
Raise transparent ray depth to 64 for this avatar's eleven iris layers.

Reference: https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/Materials/MigrationMToonMaterial.cs

Bake only the glTF baseColorFactor RGB into each material's diffuse DDS, in
linear color space (decode sRGB, multiply, encode sRGB). Keep texture alpha
unchanged: the existing NIF shader alpha already applies the alpha multiplier.
Use separate output images for different tints of a shared source image. Never
modify the original VRM or the original pose reference's shared Blender images.
Untextured materials already use a generated solid color; do not apply their
RGB factor twice. Normal/other textures must not receive the diffuse tint.

Retain geometry, weights, UVs, culling, blend/depth flags, shader opacity,
headwear records, scripts and settings. Rebuild the same follower plugin identity
as a complete replacement ZIP; this texture correction needs no save reset.
Validate shared textures with multiple tints, black/white/partial tints, alpha,
sRGB conversion, unchanged raw PNGs, actual DDS pixels and per-shape references.
Compare source and rebuilt output eye renders and full-avatar appearance; keep
private avatar data and renders local. Do not modify the installed game or saves.
