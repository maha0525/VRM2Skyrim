# VRM-only toon shading

## Shader ZIP shipped in the repository (2026-10-28)

Status: 完了 (2026-10-28: the user installed the shipped ZIP on Bottled Shaders 1.0.22 and saw the toon shading applied in game).

The user found the shader installation too hard: users had to locate the
original Community Shaders mod folder and run `toon.py --shader-root` in
PowerShell before they could use a default-on feature. Decided with the user:

- The ZIP depends only on the supported CS 1.9.0.0 sources, our patch and the
  VRM2Skyrim version, so one ZIP built by the maintainer holds the same shader
  files a user would build. Ship it: commit `toon-shader/VRM2Skyrim-Toon-Shader-<VERSION>.zip`
  to the repository. Users get it with the clone / Download ZIP they already do.
- Licence (corrected the same day from the 1.0.22 licence files): Community
  Shaders is GPL-3.0 with its Modding Exception and GPL-3.0 Linking Exception
  (`SKSE/Plugins/CommunityShaders/Licenses/COPYING.txt`, `EXCEPTIONS.md`,
  `THIRD_PARTY.md`). The MIT LICENSE that 1.0.4 kept in `Shaders/` covers only
  Ilya Perapechka's original code; CS contributors' changes to `Lighting.hlsl`
  and all of `DeferredCompositeCS.hlsl` are GPL-3.0. Redistributing the patched
  files is allowed under GPL-3.0: the ZIP carries COPYING.txt, EXCEPTIONS.md,
  THIRD_PARTY.md and LICENSE-Perapechka-MIT.txt, each patched file starts with
  a dated notice that VRM2Skyrim modified it, and the HLSL itself is the
  corresponding source. Our MIT `runtime/toon/*.hlsli` are included in the
  same ZIP and are conveyed with it under GPL-3.0; the VRM2Skyrim repository
  stays MIT, and the docs say the ZIP's contents are GPL-3.0.
- Target (decided with the user the same day): the current Nexus release,
  Bottled Shaders 1.0.22. Its DLL reports the same FileVersion 1.9.0.0 as 1.0.4
  but both shader files differ, so the DLL version cannot tell them apart. The
  Lighting patch anchors no longer match 1.0.22 and must be ported; the user
  re-verifies toon shading in game on 1.0.22.
- The wizard offers the ZIP as a download beside the STEP 01 toon checkbox and
  on the result page. No ZIP is built in the wizard.
- Shipping removes the old build-time refusal of other CS versions, so the
  wizard hashes `Data/Shaders/Lighting.hlsl` and `DeferredCompositeCS.hlsl` in
  the chosen game folder: the supported originals mean the ZIP is not installed
  yet, the patched hashes mean it is installed, anything else gets a warning
  that the ZIP is for Bottled Shaders 1.0.22 and may break rendering. When the
  files are not there (MO2 keeps them in its own mods folder), say that the
  version could not be checked and which release the ZIP is for. A warning,
  never a block: toon shading stays selectable. (The first plan read the DLL
  FileVersion; 1.0.4 and 1.0.22 share 1.9.0.0, so that check cannot work.)
- `toon.py --shader-root` stays as the maintainer's tool for rebuilding the ZIP
  after HLSL or version changes; user instructions no longer mention it. Tests
  keep the committed ZIP consistent with the code (present for the current
  VERSION, its adapter metadata matching `toon.py`), so a version bump without
  a rebuilt ZIP fails.

Sources: the user's Vortex downloads hold Bottled Shaders 1.0.4 (Nexus 192816;
its shaders match the current `SUPPORTED_LIGHTING` / `SUPPORTED_COMPOSITE`) and
1.0.22 (Lighting.hlsl 188f5016…0b90, DeferredCompositeCS.hlsl 8abca54c…a7a9).

## 0.13.0: regular feature, enabled by default

On 2026-10-17 the user accepted the complete material-effects build in Skyrim,
reported a Unity-equivalent appearance, and requested promotion to a regular
feature. Enable toon shading by default in shared settings and fresh wizard
pages, move its visible checkbox to STEP 01 beside other appearance settings,
and remove experimental wording from Japanese/English UI, conversion progress,
generated instructions and current documentation. Preserve an explicit saved
false; settings without the key use the new shared default, including after an
earlier import turned the checkbox off. Show the effective choice in review.

Use versioned shader adapter ZIP names. The existing Prototype 6 shaders and
material updates remain compatible: do not change HLSL or force another game
shader compilation for this promotion. Keep supported CS source/version checks
and real installation requirements. Verify both languages, page placement,
navigation, JSON downloads/imports and final submitted settings, then merge the
accepted effects and this promotion into main and push.

## Prototype 6: authored MatCap, rim, normals and outlines

Prototype 5 is confirmed in game and pushed to main at 7d44c34. Implement the
next effects together on codex/toon-material-effects, then deliver one shader
update for one game comparison. Do not edit the deployed game or its cache.

Read real VRM0/1 inputs and UniVRM migration/lighting definitions. Preserve
author-defined effect colours, strengths, masks and disabled settings. Keep
legacy/face-v1/source-domain-v2 markers readable and ordinary objects unchanged.
Use the proven t6 texture binding for a padded, per-region source atlas and
versioned metadata rather than assuming additional engine texture slots work.
Retain each image's resolution, addressing, colour space and normal strength.
Reconstruct tangent-space perturbation from source UV derivatives and the native
surface basis, checking orientation with an independent analytic reference.

Outlines belong to each source shape's own NIF/slot, including retained skin and
head-visibility variants. Generate a skinned inverted hull with source world
width/mask and unchanged original geometry, copying weights, bind transforms,
partitions and alpha. Source units are explicitly 70 Skyrim units per metre.
Keep generated hulls out of source triangle counts and physics/contact input;
validate their complete ownership, geometry, culling and animation separately.
None means no hull. Current Quon/Erys inputs use world widths; unsupported
screen-width semantics must be explicit rather than silently becoming world
widths. Repeated preparation must not add hulls or reuse stale originals.

Test positive effect controls plus disabled/missing maps, view/light changes,
darkness, non-target/fallback, native deferred SSGI, alpha and all four real
avatars through final validation/packaging. Inspect complete heads and full
bodies. Do not publish/merge this next prototype before user acceptance.

Verification: the complete suite passes 169 tests; 33 hardware pixel-reference
cases cover atlas addressing, controls, source normal orientation, rim and
MatCap axes. Four separate production-CS positive controls visibly change the
render. Legacy/v1/v2 material output remains byte-identical between adapters.
Quon completes real conversion, FSMP, final validation, 75 sampled animation
frames and ZIP creation. Four follower patches preserve original geometry,
normals, UVs and skin; only Quon/Erys add source-enabled world-width shells.

The user's Erys hairline observation exposed an invalid verification renderer:
it discarded transparent ZBUFFER_WRITE and rendered raw child order instead of
opaque/transparent phases. Fix the fixture, not source geometry. Preserve the
native depth flag and phases, reproduce both with overlapping-layer positive
controls, and inspect full heads against the user's normal Unity reference.
Independent Gemini image comparison rejected the initial and intermediate
frames; the corrected front/left/right comparison passed. This proves the
offline comparison's quality, not final game acceptance.

## Authored shading on every source MToon material

The user confirmed Prototype 4's face in game. Extend the same conversion to
body, hair, underwear, clothing and their derived skin/head variants, using each
shape's explicit source material. Source shade RGB/factor, ramp and equalized
ambient replace the legacy palette on all MToon materials, including constant
shade colours without a texture. Non-MToon materials keep their existing path.
Preserve geometry, alpha, skinning, physics and fitted Skyrim equipment.

The user reports ten-minute game shader compilations. Real Erys/Aifi inputs
include 2x2 and 1254x1254 shade images and clamp-to-edge addressing, which the
Prototype 4 face-only layout cannot represent. Prototype 5 metadata stores the
original image dimensions and per-axis wrap modes. Pad without resampling and
map source UVs to the exact image domain, with repeat/clamp/mirror gutters.
Keep old 8x4 and Prototype 4 face layouts readable. Package one tested shader
update together with the converter change; verify all four real avatars,
compressed metadata, invalid controls, UV seams and off-domain sampling before
asking for a single game comparison.

## Prototype 4: authored face shade through the proven texture binding

Restore face materials' own shade RGB and add equalized GI through their lit
surface, following the official MToon lighting definition and the installed
UniVRM MToon0/10 sources. Keep the legacy 8x4 path unchanged for other materials.
Face ownership comes from component/source-node provenance. Do not flatten the
face mesh or normals and do not infer face identity from shared textures.

Reuse the proven native Glowmap t6 binding. A BC7 RGB shade image has a separate
four-row metadata strip at the bottom, using constant 4x4 blocks, after repeat gutters. The shader
checks the signature/version with Load at mip 0, samples only the image domain,
with repeat gutters preventing strip bleeding. Zero native emission keeps shader-free
fallback intact. One mip avoids feeding marker RGB into shade minification;
image resolution is retained and BC7 bounds its memory cost. Validate compressed
metadata and reject unsupported UV/addressing rather than silently sampling a
different image. Completed compression caches are content-addressed and hashed.

For current followers, produce a small patch with changed head NIFs/DDS only;
do not require a full conversion. Compare the complete head, with all layers
still present, from the same front-facing camera and lighting. Include legacy
marker compatibility, native fallback, no light, alpha, deferred AO bypass,
shade-texture colour/UV edges and corrupt metadata/cache checks. MToon0's ramp
must be migrated by preserving both interval endpoints, not by copying its
different shift/toony definitions directly into MToon1.

## Face diagnosis after Prototype 3 game confirmation

The user confirmed the diagnostic is flat with SSGI enabled and the normal
prototype now looks toon-like, but Quon's cheeks still look hollow. The attached
Quon_Misaki_TH_VRM1.vrm (SHA256 7e1b1cf763779a890c3f338c054aabef8cf5363e532bdfac5b91dc6335a40b2f)
looks normal in Unity. Its actual format is legacy VRM; the previous conversion
input was VRM1, hash 3e2651b280ecafe6beae35374b863d70dcc2ec4c6becb06aa1dae5279e145fc4.
Do not infer format from the filename or compare raw array indices/coordinates:
the legacy file repeats the full vertex buffer for each primitive, while the
previous input compacts it. Indexed face positions/normals/UV agree after the
VRM coordinate rotation (-x,y,-z), to floating-point precision. No active default
morphs are present in the old input. The converter's posed source reference and
output geometry agree; normalized NIF normal error is below 0.33 degrees for
99% of vertices, with isolated maxima around 4.34 degrees. The custom-normal
reset is a general preservation concern, not an established cause here.

The source face uses a separate Misaki_face_2 shade texture, shade colour factor
1, authored MToon edge controls and rim/emission inputs. The prototype discards
shade textures and caps pale multipliers at 0.55. Prioritize restoring authored
face shading before flattening geometry/normals or asking the user to undo edits.
Keep complete head layers and identical illumination/camera in comparisons.
Audit arrays and reports: build/toon-face-normal-audit/. Actual Unity lighting
is not reproduced by the offscreen fixture; do not call source appearance matched
until that comparison succeeds.

## Activation failure: isolate before adjusting appearance

The user installed the Prototype 2 diagnostic and observed no pink. The deployed
Lighting hash matched the diagnostic, and shader cache files were regenerated;
these facts do not prove that the marked draw entered our branch.

All previous pixel shader checks forced SKINNED. Without that macro, our guard
compiled out marker recognition and the diagnostic entirely. An activation-only
probe removes that macro dependency, retaining the exact Glowmap/8x4/signature
checks and excluding landscape/PBR. It uses the delivered Prototype 2 helpers,
separate from the unfinished face/AO changes below. tests/toon_activation_probe.py
builds and checks this precise ZIP: 19 shader pairs, ordinary pixel invariance,
old no-SKINNED output identical to original, new no-SKINNED output pink. The user subsequently confirmed actual game activation with the new pink diagnostic.

## Face feedback and full deferred consumer path

The in-game face still showed concave cheek shading after Prototype 2. The
previous tests stopped at Lighting's pixel shader; DeferredCompositeCS applies
sqrt(AO) to direct diffuse after that, even with albedo/reflectance set to zero.
Carry marked-pixel ownership through a reserved non-SSS GBuffer mask value and
bypass that later AO/GI application only for marked pixels. Pin and package the
composite shader too. Exercise the real pixel -> GBuffer -> compute composite
path with varying AO; ordinary pixels must still receive the original AO.

Do not combine the AO isolation with the proposed flat-face profile yet.
The user confirmed that disabling Screen Space GI removes the residual shading
on the constant-pink diagnostic. First deliver normal/diagnostic adapters with
only activation and the later AO/GI ownership fix. Existing avatar markers and
fine-normal response stay compatible; decide further face adjustments from the
correctly activated, AO-free output.

Verification uses the real Lighting shader, native R11G11B10 mask target and
DeferredComposite compute shader, with positive AO and IL input controls.
Near-opaque blending can round 0.5 to 0.49609375 in the native mask format;
the exact non-SSS marker test allows this adjacent value, keeping x=z=0 and
rejecting native y=0/1. Test the whole ordinary image for byte invariance and
marked opaque pixels for AO/IL invariance separately; the background must keep AO.

## Prototype 2: visible bands and activation evidence

Keep existing follower NIF/DDS controls compatible. Resolve marked materials'
direct and ambient illumination together; cap pale shade multipliers while
preserving authored dark shades and their hue. Normalize by the available
unshaded light, so intense lights do not erase colour and band contrast.
Suppress forward and deferred physical reflections, wet specular and later
diffuse GI for the marked surface only. Preserve fog, alpha and world darkness.
Provide a separate optional diagnostic adapter that colours only successfully
recognized marked surfaces magenta. Never treat this offline check as a live
game capture. Deliver ZIPs; do not change the deployed game or its cache.

Compare the old/new full CS shaders with identical real avatars and lighting.
Also exercise controlled curved surfaces, intense light, no light, wrong or
missing signatures, ordinary objects, forward/deferred output and reflections.
Verify diagnostic coverage and unmarked byte/pixel invariance. Record numerical
band contrast, clipping and deferred reflectance, alongside actual images.

## User request

Apply MToon-like shading inside Skyrim only to opted-in converted VRM
characters. Keep the rest of the world on its existing rendering path.
Build a separate experimental branch from the tested FSMP converter.

## First deliverable

An optional per-material marker emitted by conversion, a compatible shader
extension for the installed Community Shaders build, and installable test
archives. Carry source MToon shade color and shadow-edge controls where the
runtime interface supports them. Preserve diffuse colors, transparency,
skinning, face/hair queues and FSMP. Keep unmarked geometry's shading path
unchanged. Never flatten the entire screen or silently replace unrelated
material types with a VRM shader.

## Investigation and verification

Read the installed shader version and its actual material bindings before
choosing the marker or injection point. Verify the marker travels from NIF
through native material upload into HLSL; do not infer an unused constant is
uploaded. Build/compile representative skinned, alpha, deferred and forward
permutations. Render the shader in an isolated D3D harness with marked and
unmarked geometry, changing light and shadow conditions. Inspect the actual
avatar output. Log shader package source version, compatibility checks and
generated material identities.

## Split-body and retained-skin material ownership

Splitting the body into torso/hands/feet must retain a material policy for every
exported shape. Copies retained inside standard-slot clothing inherit that exact
source policy as well. Record the original source shape and actual exported name
at the producing stage, and verify the binding survives export. Resolve toon
materials by those explicit bindings, never by a shared diffuse texture: different
source materials may share a texture while using different MToon or alpha settings.
Unknown shapes must still fail rather than acquiring an arbitrary material.
Verify a real wardrobe + fitting + physics + toon conversion through final
validation and packaging, including repeated export and shared-texture policies.

Do not modify the installed game, its active graphics setup or saves during
development. Deliver the optional archives with exact install/removal steps
for the user to verify in game. An offline render or compile is not proof of
the game's live drawing path.

## Implemented adapter

Use the native Glowmap technique's t6 texture binding with a private 8x4
RGBA8 signature and alpha-channel parameters. Emission remains zero. The
wrapper delegates unmarked lighting to the original EvaluateLighting;
marked materials use two-band direct lighting and flatter directional GI.
Exclude landscape and True PBR permutations; do not require SKINNED on pixel shaders. Pin the entire installed
Lighting.hlsl SHA256: the DLL's 1.9.0.0 version alone did not identify its
actual shader source. Legacy markers carry shade/lit ratios and shadow-edge
parameters. Prototype 5 adds source shade RGB and explicit image dimensions and
addressing on all source MToon materials. Outlines, matcaps and rim light remain
outside this prototype.

Compile 16 original/patched permutation pairs, and render the actual
compiled Community Shaders pixel shader against the real NIF/DDS output
in an offscreen Direct3D 11 harness. Compare unmarked, marker-only fallback
and zero-light images byte for byte. The full Aifi source conversion must
also pass geometry, physics, material and 75-frame animation readback.
