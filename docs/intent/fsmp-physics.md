# Optional FSMP physics

## User intent

### 2026-10-15 recentering precision

Aifi's 204 secondary bones exposed a native float32 bind rotation error:
singular values 1.0000299, 1.00002964, 1.00001886. FSMP recentering incorrectly
passed this existing bind through the strict rigid-offset constructor.
Keep native rotation and scale buffers exactly; recenter by translation only
and compensate skin-bind translations. Reject rotation/scale target changes.
Verify unchanged skin products, descendants and repeated-build idempotence;
reproduce using all six Spring meshes of the supplied Aifi VRM.
The full pipeline also exposed the sleeve contact proxy being included in
source appearance comparison and triangle counts. Exclude both named hidden
proxies only after validate_physics verifies their flags, skin binds, ownership
and XML. The rendered avatar retains all 113,125 source triangles and its
maximum source vertex distance is 0.000032 Skyrim units.

Keep the released converter stable on `main` (currently 0.8.1). Develop hair and cloth
physics on `codex/fsmp-physics`. Physics must be optional in the wizard;
generated physics-enabled followers use [Faster HDT-SMP](https://www.nexusmods.com/skyrimspecialedition/mods/57339)
as a runtime prerequisite. The immediate example is Quon's furisode sleeves,
which currently remain extended sideways.

## Findings from the actual Quon conversion

Read-only inspection on 2026-10-13 covered the input VRM used by the successful
Quon 0.8.0 wizard build and its saved conversion mapping.

- The VRM has 737 nodes and 29 skins. It includes dedicated sleeve and hair
  bone hierarchies and actual vertex weights to those bones.
- The `K_ACC_Sleeve` mesh has 13,232 accessor vertices. Its weights reference
  left/right `K_AccSleeve` chains as well as the arm anchors. There are 18
  sleeve nodes across the two sides, including the two roots.
- The current converter maps those sleeve nodes into the left/right Skyrim
  upper-arm bones. It maps the inspected extra hair bones into the Skyrim
  head bone. Those independent influences therefore cannot move independently
  in the current output.
- This input does not include `VRMC_springBone`, nor legacy VRM spring-bone
  settings. Erys's supplied VRM 1.0 model likewise has extra rigged bones but
  no spring-bone extension. Preserving bones alone is not equivalent to
  transferring an existing physics configuration.

The original meshes are rigged for independent motion. For this example,
source-model surgery is not a prerequisite; the converter must retain the
independent rig/weights and generate physics settings.

The local read-only evidence is in `build/physics/`: `model-springs.json`,
`weighted-bones.json`, and inspected upstream sources/guides. These files and
the source models are not committed or distributed.

## Implementation direction

1. Add an explicitly enabled FSMP option; the default disabled path retains
   current fixed appearance and native wardrobe slots. Explain the FSMP and
   matching SKSE prerequisites beside the option and in generated instructions.
2. Identify physics candidates from spring-bone metadata where available,
   actual skin influences, ancestry, and user-assigned hair/garment meshes.
   Names alone must not decide what moves. Keep humanoid animation bones
   kinematic; allow users to exclude rigid clothing/accessories.
3. Preserve selected extra bones and their vertex weights in both the private
   skeleton and appearance NIFs. Use deterministic MOD-specific names and
   preserve ancestry, full transforms, and bind poses through unit conversion,
   arm posing, secondary-rig merging, and the four-influence limit.
4. Generate private XMLs with explicit kinematic anchors, dynamic bones,
   center-of-mass offsets, joint frames, damping, gravity, and constraints.
   Use adjustable hair/cloth presets when the VRM does not contain settings;
   VRM spring parameters are not one-to-one Bullet parameters.
5. Generate collision geometry from the actual avatar, not a replacement
   Skyrim/UNP/CBBE body. Collision shape names and filters must resolve against
   the NIF that owns the XML. Plan the collision geometry separately from
   visible meshes so the avatar's displayed appearance is preserved.
6. Add root `NiStringExtraData` named exactly `HDT Skinned Mesh Physics Object`
   to each applicable NIF, pointing to its private XML. Use per-MOD paths under
   `SKSE/Plugins/hdtSkinnedMeshConfigs/vrm2skyrim/`; do not modify the global
   `defaultBBPs.xml` or other followers' assets.
7. Carry the link, bones, weights, and collision geometry through clothing
   splitting, head-visibility variants, fitted-equipment generation, and
   Outfit Studio edit/reimport. Native equip slots still control wardrobe
   exclusion; physics must not reintroduce scripted clothing replacement.

## Verification requirements

- Read back delivered NIFs and resolve every XML bone, constraint body, shape,
  and path. Validate XML against the author's schema.
- Compare bind/rest transforms and posed vertices with the original rig;
  adding physics must not alter body proportions or introduce unweighted
  vertices. Verify skeleton and mesh transforms together.
- Inspect a rendered simulation of the emitted settings, including gravity,
  moving anchors, body contact, and settling. A valid XML or bone list alone
  does not prove useful cloth motion.
- Exercise clothing equip/removal and face/hair variant changes, and verify
  coexistence of several followers with different MOD IDs.
- Keep optional-disabled output compatible with the stable converter. Do not
  require FSMP for existing fixed-appearance followers or install it into the
  user's game automatically.

The development implementation now includes retained component-specific chains,
private XMLs, hidden skinned body collision proxies, wizard settings and native
readback checks. See `docs/FSMP.md`. The stable release remains on `main`.

### Calm-default feedback

The user confirmed that the first FSMP output moves in Skyrim, but hair and
cloth oscillate excessively. The standard preset must suppress repeated sway
while allowing horizontal sleeves to fall. Fix the shared converter rather
than creating an avatar-specific tuning patch. Account for true runtime frame
coordinates, game-unit gravity, geometry-dependent inertia/damping and ordinary
solver settings in the verification. Retain adjustable softer/firmer choices.

### Attached sleeves versus hanging cloth

The 0.9.1 game test showed sleeves folding through the arms even after sway
decreased. The garment roots and close-fitting arm sleeves must follow the
animated body instead of being simulated as free cloth. Protect attachment
roots and the contiguous arm-adjacent prefix, while retaining moving distal
cloth. Use source hierarchy, actual skin influences and the avatar's collision
geometry; do not hard-code Quon's bone names or require a character-only patch.

### Static trembling and inertia agreement

The 0.9.2 sleeve attachment fix was confirmed in Skyrim, but long cloth still
trembled while the actor stood still. Correct the shared generator and offline
diagnostic using the FSMP 4.1.1 runtime's direct XML inertia semantics. Do not
treat XML inertia as a divisor or let validation simulate different inertia
from the delivered package. First isolate this correction from contact/limit
tuning. Verify stationary and moving/articulated anchors, including peak
angular motion over the settling interval, and regenerate Quon's test ZIP.

### Contact geometry must follow visible geometry

The 0.9.3 game feedback reported continued lateral sleeve motion and waist
penetration. Do not extend damping-only tuning when contact coordinates are
inconsistent. Compare the runtime render/contact transform paths and the
installed assets. For FSMP 4.1.1, avoid nonzero COM offsets by centring private
node origins, compensating binds and keeping the original XML joint pivots.
Verify skin preservation, translated/rotated contact alignment, animated
humanoid locals, removable and fixed-outfit paths, and repeat generation.

### Stationary sleeve collision feedback

The 0.9.4 screenshots show large changes in sleeve shape over seconds while the
actor stands still. Joint-only settling tests do not cover this failure. Build
an isolated contact-inclusive reproduction from the actual exported vertices,
skin weights, body proxy and XML. Fix the generated collision representation
at its source rather than asking users to change global FSMP settings. Retain
the visible sleeve geometry and skinning, animated attachment prefix, and
body contact. Identify sleeves by humanoid ancestry and their actual shared
vertex influences, including connected cloth rooted outside the arm hierarchy.
Check the removable and fixed-outfit paths and repeat generation.

## Primary references

- [FSMP source and runtime loader](https://github.com/DaymareOn/hdtSMP64/blob/dev/src/hdtDefaultBBP.cpp)
- [FSMP system creation and XML handling](https://github.com/DaymareOn/hdtSMP64/blob/dev/src/hdtSkyrimSystem.cpp)
- [FSMP author guide](https://github.com/DaymareOn/FSMP-Validator/wiki)
- [VRM spring-bone specification](https://vrm.dev/en/vrm1/springbone/)

Use these as specifications; do not copy GPL implementation code into the
original MIT modules merely to generate XML. Upstream engine or validator
tools, if used for testing, retain their own licenses.

### 2026-10-16 wizard selection persistence

Importing settings before the game catalog is available must not replay the
whole imported snapshot after STEP 01 edits. Restore only catalog-dependent
select values when their options arrive. Keep physics mesh edits through Next,
Back, locale changes, and repeated uploads of the same VRM.

Persist the physics selection with its own source fingerprint, independently
of optional wardrobe classification. Read older JSON using its appearance
fingerprint. If the source differs or a selected mesh no longer exists, show a
localized warning rather than silently appearing to have forgotten the choice;
never reuse numeric node IDs on a different VRM. Clear pending state when
starting another follower. Verify actual checkbox -> Next -> JSON download ->
new page/import/upload checkbox restoration, including both file input orders.

Verified: the new browser regression fails on the original code because the
first validation request submits [] after selecting [1,2]. The corrected UI
preserves both selections through all five steps and a downloaded-JSON import
on a fresh page, in both input orders. It also covers Back, locale switching,
same-source re-upload, disabled/enabled physics, missing/different sources,
legacy fingerprints and starting another follower. The downloaded JSON passes
actual FollowerSettings load/save; 43 related Python tests, existing combat-style
and localization browser checks, and repository Ruff checks pass.

## Body meshes and physics (2026-11-01)

When clothing or fitting cuts the body (`skin_partition_enabled`), a mesh
classified as body is written to body/hands/feet NIFs and copied under
body-slot clothing. Its movers would then belong to several files: Lucia's
sleeves crossed `body.nif` and `hands.nif`, and her bob reached the robe's skin
copy. FSMP needs one owner per mover, so those meshes cannot sway.

The wizard refuses that selection at STEP 01 and names the mesh, so the user
reclassifies it before any conversion work. Automatic physics selection skips
those meshes instead of failing. Hair is also found from material names,
because `Spring_01_bob` has no `hair` in its name, and leaving STEP 01 with no
hair mesh asks first: hair left in the body is hidden by armor and is not
switched by headwear. The question does not block, since some VRMs merge hair
into the head mesh.

Three readback checks also stopped Lucia on correct output and were corrected
in the same change: a zero-area triangle's empty normal, near-duplicate source
vertices swapping identity, and PyNifly losing the last bone-name character when
the joined names exactly fill its 300-byte buffer.

## VRM spring settings and colliders (2026-11-02)

Measured on DeepSeek-chan.vrm (VRM 1.0, 40 springs, 11 colliders in 4 groups):
only the list of spring joints was read. Skirt joints have stiffness 8,
gravityPower 0.12, hitRadius 0.025 and the LegGuard group, but every mover got
gravity-factor 1 and a spring about 1/10 of the gravity torque, so a flared hem
fell nearly vertical. Contact used only the leg's real hull, smaller than the
VRM's 0.12 m thigh capsule, so legs passed through it.

The outcome: a mover covered by a VRM spring keeps the VRM's rest shape and is
kept off the VRM's colliders. A VRM without springs or colliders keeps the same
gravity, stiffness, margins, tags and shapes as before; only `physics.json`
gains two empty fields per system. The number of contact points per bone does
not change.

Joint rule. VRM's steady direction is proportional to
`stiffness*rest_dir + gravityPower*gravity_dir`, so its droop satisfies
`tan(a) ~= (gravity/stiffness)*sin(tilt)`. The joint spring is `joint_profile`
called with `physics_stiffness * stiffness / SPRING_REFERENCE_STIFFNESS`.
gravity-factor is `k*(gravity/stiffness)/(mass*GRAVITY*length)` clamped to 0..1,
with k that spring and length the norm of the com; stiffness 0 gives 1. Since k
scales the factor, the droop does not depend on the stiffness preset, which now
changes only how far a mover swings. Damping uses the scaled gravity. Bones
without their own settings inherit from the nearest ancestor that has them.

Contact rule. FSMP collides only mesh shapes, so each collider group used by a
mover in a system becomes a hidden closed per-triangle mesh
`V2SCollision_Spring{group}`, rigid on the NPC bones, at radius minus the
triangle margin. A mover's patch has margin `max(.4, hit_radius*70)`, so contact
distance is VRM radius + hitRadius, and it can collide with the body tag plus
each of its group tags. Patches are therefore partitioned by (margin, groups)
before the `SHAPE_BONE_LIMIT` chunks; the default class keeps today's names, the
others are `<base>_S{n}`. The contact point's required clearance from the body
hulls is per bone: its margin + .35 + .05, which is .8 by default.
A bone whose rest contact point is inside a collider of a group drops that
group, because a sphere starting inside a closed mesh gets an inward contact. It
keeps the body tag. `rest_inside_colliders` in `physics.json` records this, and
`validate_physics` re-derives it from `spring-colliders.json`.

VRM 0 offsets are not glTF node-local. On AnimalKawaii_01_Kuro.vrm x keeps its
sign: left arm offsets run towards -x and right arm offsets towards +x, the
child directions of those arm nodes. z must be negated: forearm offsets have
z/x -0.00175 against a limb direction of +0.00176, and thigh offsets mirror the
limb the same way, so they lie on the limb only after negation. The chest and
head spheres also protrude less from the skin once negated. VRM 1.0 colliders
were checked against DeepSeek's finished skeleton: thigh, calf and foot capsules
start at their bones.

Not used: dragForce, gravityDir and center. `SPRING_REFERENCE_STIFFNESS` (2.0) is
a tuning value and has not been validated in game; neither has the skirt's
behaviour against the capsules.

Known limits. The droop rule is per joint: an upstream joint also carries its
children's scaled weight, so a chain can droop somewhat more than VRM at its
root. FSMP's default triangle penetration of 1 unit still applies, so a patch
pushed deeper than that into a capsule in one step gets no contact. Blender has
no per-body gravity, so `physics_preview_blender.py` does not simulate
gravity-factor.

These surfaces are wider than the body, so they are `shared` internal: only the
same skeleton's shapes can touch them. Other actors' cloth sees only the body proxy.

Converted through the whole pipeline: DeepSeek-chan (VRM 1, fixed appearance),
Lucia (VRM 1, removable wardrobe) and AnimalKawaii_01_Kuro (VRM 0). The VRM 0
offset rule matches UniGLTF's z reversal and the limb axes; its front/back
placement on the torso was not checked in game.
