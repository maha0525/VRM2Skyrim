# FSMP development verification

Verified on 2026-10-13 with Blender 4.5.12 and the local pinned PyNifly runtime.
Private VRMs and generated game assets remain outside Git.

- 58 Python tests pass, including native NIF save/reload, hidden collision
  proxy skinning, preserved skeleton transforms, private links, component
  ownership, source spring formats and root pivot/centre-of-mass cancellation.
- Ruff passes for all changed Python modules.
- A separate headless browser exercises the actual wizard FSMP checkbox,
  mesh selection, stiffness control and settings download. Defaults are off.
- Quon's real VRM converts through both fixed-outfit and removable-wardrobe
  pipelines. Both preserve all 279,116 source triangles; the visible wardrobe
  output has 52 shapes. Collision proxies are checked separately.
- Five wardrobe/visibility XMLs and the fixed-outfit XML validate against the
  FSMP author's schema 2.2.0. All links, bones, constraint bodies, contact
  shapes, weights and body collision bind poses resolve in delivered files.
- The wardrobe output has independent systems for hair, two clothing groups
  and the corresponding head variants. Simultaneously worn components have
  disjoint dynamic bones and distinct collision tags.
- An offline Bullet joint preview reads the emitted XML for 216 dynamic bones,
  applies gravity and a moving-anchor excursion, and samples 1,800 frames.
  Maximum pivot separation is 0.00982 game units; final maximum speed is
  0.128 game units/second. Rendered delivered meshes show the extended sleeves
  hanging down. This is the documented joint-only diagnostic; FSMP implements
  runtime skinned-mesh contacts.
- Full official equipment regeneration covers 2,986 original items, 3,076
  addon bindings and 483 distinct models. Readback verifies original body
  coverage, normals, UVs, skin bindings and private-race addon records.
- Walk and sword-attack HKX checks cover 75 animation frames and preserve
  the custom limb proportions.
- Repeating clothing skin generation excludes old generated skin and physics
  proxies before rebuilding. Final FSMP readback confirms the recreated hidden
  proxies and their XML links.
- Compared with Quon's previous all-official build, the original item/addon
  associations, private addon FormIDs and head visibility policies are unchanged.
  Its existing combined armor compatibility patch can therefore remain installed.
- The final installable ZIP passes CRC validation and contains all five linked
  XMLs plus the exact settings used to produce it.

Local evidence: `build/physics/Quon_FSMP_210325/`, the fixed-outfit test build,
`build/physics/ui/`, and the local FSMP author schema. The installer does not
modify the game folder or install FSMP.
