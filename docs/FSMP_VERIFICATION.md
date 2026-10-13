# FSMP development verification

Foundation verified on 2026-10-13; calm profile verified on 2026-10-14 with
Blender 4.5.12 and the local pinned PyNifly runtime.
Private VRMs and generated game assets remain outside Git.

- 60 Python tests pass, including native NIF save/reload, hidden collision
  proxy skinning, preserved skeleton transforms, private links, component
  ownership, source spring formats, bone-local joint frames, long-cloth damping,
  gravity-aligned swing/twist limits and lighter distal-chain mass.
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
- The original preview used metre-valued gravity on game-unit coordinates
  and interpreted `frameInB` as rigid-body-local. Its former settling figures
  did not validate the runtime configuration and have been superseded.
- The revised joint-only Bullet diagnostic uses Spring2 constraints, FSMP
  bone-local frames, the emitted inertia divisor, gravity 687.7193 game units/s²,
  16 solver iterations and 60 Hz steps (two steps at 30 fps). It verifies that
  Blender retains the actual exported spring-damping coefficients.
- 216 dynamic bones settle, follow a 30-unit anchor excursion and 35-degree
  turn during seconds 2–4, then settle again over a 15-second run. Results:

  | Output / frame rate | Final max speed | Last-second RMS speed | Max settled pivot gap |
  | --- | ---: | ---: | ---: |
  | Old profile / 60 fps | 45.1334 | 8.57260 | not measured |
  | Calm / 30 fps | 0.05920 | 0.01414 | 0.32666 |
  | Calm / 60 fps | 0.05786 | 0.01594 | 0.32667 |
  | Calm / 120 fps | 0.05895 | 0.01462 | 0.08167 |

  Distances are game units, speeds game units/s. At 60 fps, residual RMS speed
  decreases by 99.81%. Raw peak pivot separation during motion is 1.11712;
  after allowing the measured one-frame travel of an animated kinematic anchor,
  the largest solver gap is 0.70127. Dynamic-to-dynamic gaps receive no allowance.
  Acceptance limits are 1.0 solver gap, 0.4 settled gap (the cloth contact margin),
  and final speed below 1.0. All three frame rates pass. Runtime mesh contacts
  remain FSMP's skinned-mesh implementation; the diagnostic disables rigid
  bone-body contacts, matching the runtime's bone collision mask.
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
- The 0.9.1-dev archive differs from 0.9.0-dev only in the five private physics
  XMLs and generated README. Every ESP, NIF, DDS, DLL and other packaged file
  has the same SHA256. Existing saves and the armor compatibility patch retain
  the same record IDs and files; no plugin reset or armor-patch rebuild is needed
  for this tuning update. Replace the follower archive, deploy and restart Skyrim.

Local evidence: `build/physics/Quon_FSMP_0.9.1/`, the old `Quon_FSMP_210325/` comparison, the fixed-outfit test build,
`build/physics/ui/`, and the local FSMP author schema. The installer does not
modify the game folder or install FSMP.
