"""Per-shape limits of the Skyrim SE NIF skin, shared by the Blender export, FSMP and validation."""

# A skinned vertex stores its bone indices as bytes, so one shape addresses at most 256
# bones; a written shape with more maps the rest onto earlier bones.
SHAPE_BONE_CAPACITY = 256
# Exports split shapes below the capacity, within the largest shape already seen
# working in game (108 bones).
SHAPE_BONE_LIMIT = 100
