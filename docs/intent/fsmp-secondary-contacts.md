# Stable hair and non-sleeve cloth contacts

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
