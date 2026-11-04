"""Per-shape limits of the Skyrim SE NIF skin, shared by the Blender export, FSMP and validation."""

# A skinned vertex stores its bone indices as bytes, so one shape addresses at most 256
# bones; a written shape with more maps the rest onto earlier bones.
SHAPE_BONE_CAPACITY = 256
# Exports split rendered shapes to at most this many bones. Skyrim SE crashed while
# drawing a 100-bone hair shape (Erystelis, 2026-11-05: memcpy overrun in the skinned
# depth pass); the same hair split into shapes of 60 or fewer bones drew without a crash.
SHAPE_BONE_LIMIT = 60
