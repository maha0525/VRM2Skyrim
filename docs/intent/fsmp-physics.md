# Optional FSMP physics

## User intent

Keep the released 0.8.0 converter stable on `main`. Develop hair and cloth
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

This document records feasibility findings and the intended implementation;
it does not mark FSMP support as released or implemented.

## Primary references

- [FSMP source and runtime loader](https://github.com/DaymareOn/hdtSMP64/blob/dev/src/hdtDefaultBBP.cpp)
- [FSMP system creation and XML handling](https://github.com/DaymareOn/hdtSMP64/blob/dev/src/hdtSkyrimSystem.cpp)
- [FSMP author guide](https://github.com/DaymareOn/FSMP-Validator/wiki)
- [VRM spring-bone specification](https://vrm.dev/en/vrm1/springbone/)

Use these as specifications; do not copy GPL implementation code into the
original MIT modules merely to generate XML. Upstream engine or validator
tools, if used for testing, retain their own licenses.
