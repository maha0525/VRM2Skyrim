# Reuse existing equipment texture paths

All-official fitting copied roughly 2 GiB of existing equipment DDS images into
each follower; textures represented 93% of a real 1.45 GiB MOD ZIP. Keep fitted
geometry and private avatar textures, but reuse unchanged official textures at
their game paths. Do not downsample, recompress images or change material values.

Require the path to exist in an installed official archive, and exact content
comparison with the currently resolved game image. Under the installed profile,
a deployed replacement at a native game path can also be shared; the original
archive guarantees the path still exists without the replacer. Under the official
profile, retain original image bytes even when a deployed replacer differs.
Mod-only paths and uncertain optional archive overrides stay private and bundled.
Unknown/missing official assets remain private. Leave unrelated game files alone.

Record the archive, canonical texture path, original and selected SHA256 for every shared dependency.
Verify those dependencies through the actual armor validator and package gate;
never permit arbitrary missing/external textures. Preserve unique decoded preview
images for different directories with identical basenames, and keep the edit kit
and cached previews working. Both weight variants must remain identical.

Verify using a copy of the real all-equipment output and a fresh representative
conversion: unchanged geometry/UVs/normals/weights, identical selected texture bytes,
same rendered preview, complete ZIP and shared-dependency acceptance/rejection.
Report compressed texture/mesh totals before and after, not just file counts.


Stage the shared DDS images under the preview work directory in the application
runtime before Blender imports any NIF. Blender needs discoverable source images
to create material nodes; redirecting existing image nodes afterward is insufficient.
Keep BSA/LZ4 extraction in the application runtime, and include preview DDS files
in cache readiness checks. Read back lighting and effect shader references before
retiring private copies. Keep both weight variants and all shader flags intact.
