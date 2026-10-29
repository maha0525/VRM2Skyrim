# Stable hair and non-sleeve cloth contacts

## Fixed-avatar attachment duplication (2026-10-15)

Aifi's fixed-appearance ARMA advertised ten model slots while every visible
NIF partition used slot 32. With FSMP 4.1.1 the runtime log showed ten complete
251-bone systems, and profiling counted 200 contact shape pairs per substep.
Changing only that ARMA mask to slot 32 reduced construction to one system
(251 bones); the user confirmed the game became substantially lighter.
The original secondary contacts, joints, meshes and shaders remained enabled.

Generate fixed-avatar ARMA coverage on slot 32, matching the exported NIF.
Keep the ARMO occupancy mask on all original ten slots: equipment exclusion
and model attachment are separate responsibilities. Preserve all FormIDs,
outfits, physics and wardrobe-specific coverage. Apply this to fixed output
with physics both enabled and disabled, and verify the serialized plugin.
Evidence and controlled overrides are in `build/fsmp-freeze-20261015/`.

## Secondary contact geometry

Aifi keeps moving at rest with stiffness=1; generated and installed XML match.
Only 60 of its 152 movers use rigid contact patches. The remaining hair,
skirt and cape contacts use blended visual vertices, allowing a single
contact to act on multiple bones, including small-weight influences.

Extend single-owner contact patches to all movers. Retain the established
sleeve proxy and add a secondary proxy for other bones. Derive every mass
centre from actual skin weights. Preserve visible geometry, weights,
materials, rest skin products, humanoid transforms, attachment rules and IDs.
Keep body collision and the calm joint profile; do not hide instability by
disabling physics or freezing the avatar's distal hair and cloth.

Do not generate active contacts on unweighted intermediate chain helpers.
Their pivot can lie inside an animated limb, although they have no visible
surface of their own. Retain their joints and dynamics, but explicitly filter
their rigid proxy vertices with weight-threshold=1. Native validation derives
this exclusion from the original visible skin, not source names or presets.

A wrapped sleeve or curved hair can have its mass centre inside the body.
Keep the weighted CoM for dynamics, but place its rigid contact patch on a
strongly weighted original surface sample near that CoM, preferring at least
0.8 game units of clearance from every rest-body hull. This exceeds the 0.75
combined contact margins. If no clear candidate exists, use the nearest
strong real surface sample. Record every selected point and validate it
against original visible skin, keeping all binds conventional and rigid.
Preserve the established sleeve mass-centre contact when it already has that
clearance. Moving every sleeve contact unnecessarily regressed Quon's calm
motion; preserving clear centres retained its stable result and improved
Aifi's post-motion settling too.

Compare delivered Aifi and Quon assets in an isolated Bullet diagnostic with
FSMP 4.1.1 contact merging, filtering and constraint setup, at 30/60/120 FPS
and with stationary/moving anchors. Check native proxy ownership, frames,
single-owner weights, exclusion of visual contact feedback and idempotence.
Inspect actual rendered output and supply a complete follower ZIP; do not
deploy into the live game. In-game movement is the user's visual check.

## Shapes within the NIF bone capacity (2026-10-29)

A skinned NIF vertex stores its bone indices as bytes, so one shape addresses
at most 256 bones. Erystelis' hair (`Spring_04_hair`) exported two visible
shapes with 809 and 812 bones and one secondary contact shape with 582 bones.
In the written files no vertex was weighted to bone 256 or later: those
vertices followed earlier bones instead. The visible hair would have deformed
with the wrong bones; only the contact patch check stopped the conversion.

Split every exported shape to at most `SHAPE_BONE_LIMIT` (100) bones, within
the largest shape already seen working in game (108). `partition_shape` cuts
visible meshes by faces and keeps only the bones each part is weighted to.
Contact patches split into `V2SCollision_ArmCloth` / `V2SCollision_Secondary`
plus numbered shapes (`_001`, ...), each declared in the XML with its own
helper exclusions. Validation refuses any shape over 256 bones, so a NIF with
remapped weights is never packaged.

Not yet verified in game: whether FSMP stays responsive with about 590
movers in one system (Aifi's 251-bone systems were noticeably heavy when
duplicated).
