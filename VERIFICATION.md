# VRM2Skyrim verification

## 0.9.4-dev render/contact frame consistency (2026-10-14)

Read-only hashes of the installed Quon XMLs matched 0.9.3. The installed log
reported FSMP 4.1.1. Tracing its collision update and visible-node write paths
revealed inverse(COM)*rigWorld versus rigWorld*inverse(COM) composition. A
Quon draped-pose diagnostic reproduced a 16.963-unit frame displacement at
90-degree actor yaw. Moving the native private origins to mass centres and
emitting identity COM reduces this render/contact frame difference to zero,
including translated actors at 0/90/180-degree yaw.

Native tests exercise shifted parent and retained child frames, compensated
skin binds, XML pivot preservation, rotated render/contact matrices and repeat
generation. Actual asset comparisons preserve vertices, triangles, bone
weights, textures and rest boneWorld*skinBind products across all 12 appearance
NIFs. The original humanoid locals and limb lengths remain valid across all
75 walk/attack frames. Float32 hierarchy roundoff is tolerated at 0.0005 game
units for change detection, within the existing 0.001 native readback bound.

65 tests and Ruff pass. Five XMLs pass the FSMP schema/native validation and
all five 15-second stationary/moving/arm/30/60/120-fps joint diagnostics pass.
Both removable clothing and the fixed-outfit path retain 26 protected garment
attachments and 192 movers. Repeated native frame/XML generation is byte
idempotent. Local evidence and the installable sample are under
`build/physics/Quon_FSMP_0.9.4`; fixed-outfit evidence is under
`build/physics/Quon_FSMP_fixed_0.9.4`.

## 0.9.3-dev direct FSMP inertia (2026-10-14)

The FSMP 4.1.1 XML reader passes `inertia` directly through its rigid-body
constructor to Bullet 3.25. The previous generator wrote a constant 0.2 while
the diagnostic interpreted it as a shape-inertia divisor. The shared generator
now writes geometry/mass-scaled explicit inertia; the diagnostic recreates that
same tensor from XML. Runtime-consumer tests cover a long and short weighted
chain, torque response, and rejection of unsupported/invalid preview tensors.

The 0.9.2 Quon XML, interpreted with the correct direct-inertia semantics,
failed the joint/settling diagnostic: peak final-second speed 1.448 game units/s
and settled joint gap 4.070 units. The regenerated 0.9.3 XML passes all five
15-second diagnostic runs with the same 192 dynamic bones and 26 protected
garment attachment bones:

| Anchors / frame rate | Peak settled speed, game units/s | Peak angular speed, rad/s |
| --- | ---: | ---: |
| Move/turn, 30 fps | 0.04670 | 0.02626 |
| Move/turn, 60 fps | 0.06378 | 0.04423 |
| Stationary, 60 fps | 0.06028 | 0.04199 |
| Move/turn and bend arms, 60 fps | 0.09676 | 0.04421 |
| Move/turn, 120 fps | 0.04065 | 0.02639 |

The new peak-angle check uses an atan2 skew/trace angle. Comparing an actual
rounded 120-fps final pose with itself reproduced an erroneous 0.116 rad/s
under acos(trace); a regression test requires zero motion for repeated rounded
poses while preserving known nonzero rotations. Limits are 0.25 units/s and
0.1 rad/s over the complete final second. This is the joint/gravity diagnostic
described in `docs/FSMP.md`, with 16 solver iterations and private bones.

64 Python tests and Ruff pass. All five generated XMLs pass the FSMP schema
and native NIF-link, bone, skin-weight, collision-proxy and bind-pose validation.
XML regeneration is deterministic. Asset hashes show only the five physics XMLs
changed from 0.9.2; ESP, NIF, DDS and runtime assets retain their original bytes.
The settled pose was rendered from the delivered NIF/DDS assets. Local results
and the installable Quon sample are under `build/physics/Quon_FSMP_0.9.3`.

## 0.8.1 Direct3D texture dimensions (2026-10-13)

The installed Erys 2x2 BC7 DDS reproduced E_INVALIDARG (0x80070057) when its
actual mip payloads were submitted to a hardware D3D11 device. Engine Fixes
records that code as "texture load failed unexpectedly". Conversion now uses
uncompressed RGBA8 for top-level dimensions not divisible by four, without
resizing or changing the source image. Aligned images keep the previous BC7
encoding. Emitted and referenced DDS headers are checked for dimensions,
format, mip count, and recognized-format payload length before preview decode.

56 Python tests and Ruff pass. Native texconv tests cover 1x1, 2x2, 3x5, 6x2,
4x4 and 8x4 sources, preserve exact RGBA pixels in uncompressed output, and
retain source PNG hashes on repeated conversion. Regression fixtures reject
the previously accepted 2x2 BC7 case and truncated/invalid mip storage, while
accepting the legal 2x2/1x1 lower mips of aligned compressed textures.

The final Erys 0.8.1 archive passes existing NIF/plugin validation (56 shapes,
222399 triangles, 515 records). All 17 regenerated avatar DDSs, including the
corrected 2x2 RGBA8 image, load successfully through D3D11 texture creation.
Archive comparison shows only the corrected DDS and generated version readme
changed; the ESP, skeleton, meshes, equipment assets, remaining textures and
settings retain their original bytes. The corrected image retains exact source
pixels. Original archives and game Data were preserved. Local evidence is in
build/texture-load and build/texture-fix/ErysWardrobe_0.8.1_final.

## 0.8.0 native wardrobe and wizard corrections (2026-10-13)

Retired the asynchronous OnObjectEquipped clothing-removal policy. Native ARMO
slot masks now exclude torso outfits (32), gloves (33) and shoes (37); ARMA
coverage separately retains displaced original skin. Simultaneously worn torso
clothes form one inventory item. Extended slots mean intentional coexistence.
Only the one-time initial equip remains. The shipped PEX and every generated
private wardrobe PEX are checked for absence of unequip/outfit/inventory-reset
calls. Delayed events are inert. Native profiles do not populate replacement
lists through the combined armor patch; legacy profiles remain supported.

49 Python tests and Ruff pass. Deferred equip-event tests use the actual
generated ARMO masks and execute shipped PEX bytes. Tests reject same-count
duplicated faces and changed triangulation. Original skin face matching uses
one-to-one geometric/UV correspondence rather than rounded bins, avoiding the
48 false mismatches observed on float32 re-export of the second private avatar.
Coordinate/UV, normal and normalized-weight checks retain their thresholds.

Two ordinary full official-equipment outputs retain respectively 222399/279116
source triangles and 20464/39832 original skin faces. Each has 483 fitted models,
3076 bindings and a 2986-item armor patch; 75 sampled animation frames preserve
limb lengths. Standard clothing copies preserve original source skin. The first
avatar's five legacy garments become a torso set and shoes, retaining survivor
record indices 0/4. The second keeps separate torso, hands, accessory and feet.
All source inputs and generated game/avatar assets remain local.

Special native head partitions (130/131/141/142/143) survive export and native
readback, including meshes with both 31 and 131. Large/multi-material duplicate
names are normalized before PyNifly export; the original second-avatar model
conversion no longer loses its material mapping. Its full generated output was
completed after correcting the readback checker, without mesh repair. A fresh
real wizard Create-button run with the same VRM/wardrobe and three representative
fitted items separately completed with the final checker and native policy.

Headless Chrome exercised native regional defaults, a full outfit, conflict
rejection without slot fallback, manual standard/extended slots, legacy migration
notice and export/reimport. The actual head-preview button generated fitted
helmet close-ups; face/hair changes reused geometry and changed rendered parts.
The resulting image was inspected. Compact head settings/reset, class wording
and learned-spell filtering were exercised. Generated garment IDs avoid the
body/hands/feet component namespace; conflicting manual IDs fail before export.

Per-avatar patch status checks compare deployed ARMO-to-private-ARMA bindings.
Single/combined patch downloads retain original armor masks/stats. The wizard
explains source-body selection, labels inferred assignments clearly, places
grouping/add controls with generated garments, and shows a single selected
headgear policy rather than expanding all helmets at once.

## 0.7.0 official equipment / head policies / finishing (2026-10-12)

The final private Erys conversion covers 2986 distinct playable humanoid ARMO
items from nine installed official plugins, with 3076 item/addon bindings and
483 unique fitted addon meshes. Shared male models used by female actors,
including iron shields, are included. Enchanted variants reuse geometry.
The follower has 521 private records; the combined patch has 2986 ARMO,
78 footstep ARMA overrides and five equipment/visibility FLST overrides
(3069 records). Original armor data and localized names are read back against
the remapped installed masters. A real second, deployed-reference follower was
also combined into one patch successfully.

All 222399 original VRM triangles and 20464 original skin faces are retained.
Partitioned/copied skin preserves its source positions, UVs and normals;
minimum normal cosine is 0.9999817029985892. Both fitted weight variants are
identical. Every delivered fitting NIF is checked for SE format, resolved
textures, valid bones/partitions, normalized weights and finite coordinates.
Vanilla walk/attack sampling retains original limb lengths in all 75 frames.
Actual delivered iron and stalhrim gear, including helmets and shields, was
imported, rendered and visually inspected; the iron set was also rendered with
the native sword-attack animation.

The four permanent visibility states contain 38/31/7/0 shapes. Exact source
geometry, UVs, normals, transforms, bone weights, texture paths, alpha settings
and shader flags are compared against the separate original face/hair parts.
Native FaceGen remains disabled. Shipped compiled PEX tests exercise equip,
unequip, load and NiNode events, independent face/hair policies, refresh-loop
prevention, all clothing groups and equip ordering. Large equipment lists use
actual worn slots instead of walking every enchanted variant. One item that
replaces multiple groups removes every corresponding original garment.

A genuinely modified NIF was imported and its changed surface reproduced in
two separate Blender regenerations. An actual NIF with modified original skin
was rejected before persistence. Failure injection restores prior meshes and
saved overrides. Stable partition names and NIF/Blender UV-origin conversion
are included in this path. The edit fixture was removed and the delivered
meshes restored byte-for-byte afterwards.

A fresh deployed-reference conversion completed from VRM input to validated
follower/patch/edit-kit ZIPs with five representative body/boots/head/shield/DLC
items. Its reference female-body file is byte-identical to the installed UNP
body (6850 vertices), demonstrating unequal source/target topology through the
real fitting pipeline. The official profile separately uses archive-native
body and equipment rather than mixing them with deployed body replacers.

Headless Chrome tests operate the wizard's saved-result reopening, fitting
range/reference controls, male/female catalog switching, independent head
policies and JSON export/reimport. Completed job metadata survives restart.
Clothes-only conversions keep the classified face/hair in a single permanent
addon. The full 42 Python tests and Ruff pass.

The final follower ZIP's every entry was hashed against its validated MOD
folder and package manifest. SHA256:
`da16f8ddc6e19f72349c2f974e992148497edbd3c220f4987709a43942d8fe88`.
Private inputs, reference assets, screenshots, renders, edited fixtures and
generated MOD archives remain local; only generic source/docs/runtime are
published. Head visibility uses SKSE64.

## 0.6.2 source-material culling (2026-10-12)

The user reported the 0.6.1 wardrobe update worked, then supplied close-up images
of thick dark strips over the sclera. The original face materials are
doubleSided=false, use intact white sclera textures, and all twenty default face
morphs evaluate to zero. The converter forced every material to DOUBLE_SIDED.
Same-source, same-camera A/B renders differing only in backface visibility
reproduce/remove the strip. Ray casts through the strip identify a back-facing
eyelash-material triangle before the front-facing eye. This identifies the
producer's material-setting error, not missing avatar preparation.

Exports now preserve source sidedness independently of alphaMode and depth write.
New export checks read the native NIF flag back. Shape metadata enables the final
validator to reject culling drift. Cycles previews explicitly hide back-facing
surfaces for single-sided materials, preserving existing surface/alpha shaders
and leaving explicit double-sided materials intact. Source previews use stable
material names so duplicate/long names cannot lose their material policy.

All 32 local Python checks and Ruff pass. Native synthetic-NIF tests cover each
opaque/masked/blended and single/double combination, repeated application, alpha
property preservation, geometry and unrelated flags. A fresh conversion from the
private source avatar exports 52 original shapes: 19 single-sided and 33 explicitly
double-sided. Independent per-name native readback matches every source policy.
Both source and exported-NIF production preview paths were run, and same-camera
eye close-ups of the delivered NIF were visually inspected.

The delivered private output preserves every vertex, triangle, UV, normal, bone
name, weight, transform, partition, alpha mode/value and texture. Only the
DOUBLE_SIDED flag changes where the source is single-sided, including original
skin copied into fitted equipment. All DDS files, follower ESP, private wardrobe
PEX and armor-patch ESP remain byte-identical to 0.6.1. Native geometry validation
retains 222399 original triangles, 20464 body faces and 33 private records.
The ZIP was checked against the validated folder byte-for-byte. Avatar source,
screenshots, renders and generated MODs remain local.

## 0.6.1 equipment priority and garment classification (2026-10-12)

The user confirmed that 0.6.0 renders the original VRM face with the fitted
cuirass/boots in normal follower use. AFT equipment management had not been
enabled in that successful test. The user also observed tights displacing the
cuirass and UI labels showing skirt as cloak and tights as backpack. The source
used last-equipped-wins in both directions, and sequential garment slots 46/47
explain those UI labels. These are separate mechanisms.

0.6.1 makes fitted gear win in either equip-event order, including repeated
clothing equips. Original clothes can be worn after removing corresponding gear;
accessories and all inventory counts remain untouched. The real shipped PEX
bytes are tested for all three groups, both event orders, repeated equip attempts,
delayed events and empty/replaced equipment states. All 29 Python tests and Ruff
pass. These tests use native actor mocks, not the engine's equipment AI.

The wizard exposes garment usage, slot purpose and replacement group separately.
The headless Chrome select -> download -> reimport test verifies all three
fields. New splits prefer generic layers over cloak/backpack slots. Proper native
vendor and garment-usage keywords are written and read back from the plugin.
Usage keywords do not promise an independently selected SkyUI subtype/icon.

The private local test output was rebuilt with the original garment FormIDs and
new layers 53-57. All five garment NIFs preserve their exact vertices, triangles,
UVs, normals, weights, bone names, textures and shape transforms; only partitions
change. Every other NIF/DDS is byte-identical to 0.6.0. Readback retains all
222399 source triangles, 20464 original body faces and 33 private records. The
final garment NIFs were imported and rendered in Blender with the original
wardrobe, then visually inspected. The armor-patch ESP is byte-identical to the
previous patch, and installed paths remain disjoint from the existing fixed-mode
follower ZIP. Every ZIP entry equals its validated mod-folder file.

The new runtime's Skyrim behavior, updating a saved follower's changed layer
masks and AFT equipment management still require in-game confirmation. No
Skyrim/Vortex UI was operated. Existing successful game feedback is evidence
for 0.6.0's face and fitted appearance, not for these new priority/layer changes.

## 0.6.0 independent head / inventory / switching (2026-10-12)

The user confirmed fitted banded iron armor renders in 0.5.1, but overlaps the
VRM garments. Normal inventory hides default-outfit garments. Installed AFT
source shows RemoveAllItems and SetOutfit(TweakNoOutfit) during inventory control;
the user observed the 0.5.1 head cover disappears and the dark human face returns.
The 0.5.1 equipment-head workaround is superseded, not considered AFT compatible.

The private race disables FaceGen Head (DATA bit 1, value 0x2); NPC/race head
references are private empty HDPT/FaceGen assets. Readback verifies empty BSFadeNode
assets, no human head refs and no required equipped cover. All source NIF/DDS
bytes remain identical. Clothes are CNTO inventory items, with empty OTFT.
Private per-follower PEX/VMAD/FLST bindings implement initial wear once and
body/hands/feet mutual exclusion, leaving accessories alone. No periodic reset,
SetOutfit, AddItem, RemoveItem or inventory transfer is performed by the runtime.

All 27 local Python checks and Ruff pass. The shipped, renamed PEX bytes are
parsed and executed with a strict test VM and in-memory native actor calls.
Tests cover clothing -> cuirass -> boots, reverse changes, inventory preservation,
initialization for existing teammates, every item removed, OnLoad overlap repair
and stale queued equip events. This proves the bytecode logic under those native
API assumptions; it does not reproduce the engine rendering/outfit AI or AFT VM.
The final fitted output retains all source triangles/body faces and shading
normals, and every packaged byte matches the validated
folder. Skyrim/AFT runtime appearance, migration and saved inventory remain
awaiting game confirmation. No game/Vortex UI was operated by the agent.
The real headless Chrome select/download/reimport path preserves the new
equipment-group selection. Default boot/shoe names suggest feet; the user can
override that suggestion or choose accessory explicitly.


## 0.5.1 native-head correction (2026-10-12)

The user observed a vanilla human face over the VRM appearance in the 0.4.1
wardrobe build. Reading the delivered plugin confirms inherited NPC head parts
and no head-covering worn item. The same fault exists in 0.5.0 fitting mode.
The user-confirmed fixed mode equips its head-covering Appearance ARMO instead.
Source-backed worn-mask checks now reject the two old wardrobe outputs and accept
fixed mode. A non-playable, meshless head cover is included in new wardrobe
outfits; its mask covers native head slots without touching VRM face Skin slot 60.
Tests check default clothing, every garment removed, fitting/non-fitting modes,
missing-cover rejection, and accidental slot-60 hiding rejection.
All 24 Python tests and Ruff pass locally. Both existing wardrobe and fitted
outputs were rebuilt and validated: 222399 original triangles, with every NIF
and DDS byte unchanged from their respective earlier outputs. Private record
counts are 20/24. Every ZIP entry was compared with the validated mod folder,
and installed paths remain disjoint from the existing fixed-mode follower.

The earlier NIF render harness displayed exported components but omitted the
game-generated head. That render check could not establish final in-game face
appearance. Engine-generated geometry must be considered separately from the
exported meshes; binary head hiding and geometry checks are distinct evidence.
The new head cover's in-game appearance, saved-NPC outfit migration, follower
inventory/dismissal/reload behavior and interaction with equipment managers are
not yet user-confirmed. Existing saves can equip the new head-cover FormID without
deleting the follower. This change does not correct lighting/material brightness.

## 0.5.0 selected equipment fitting (2026-10-12)

Twenty-three Python tests and Ruff pass. Synthetic geometry checks require the
equipment field to change equipment while leaving its read-only target skin
untouched, including repeated auxiliary-bone contributions. A local master test
combines two follower masters, retains both private addons and all original item
stats/addons, resolves localized names correctly, and rejects duplicate profiles.

A private local separable VRM was converted through actual headless Chrome
operations: wardrobe classification, equipment checkbox/selection, settings
download/import, conversion, output image loading, follower ZIP download, and the
combined-patch button/ZIP download. Desktop and mobile pages are visually checked.
The exact final output is used for subsequent readback and render checks.

The reference skin is split into torso, hands and feet without moving target skin
vertices. Readback verifies complete original triangle coverage and winding, UVs
and normals, with seam/coincident-corner matching. A development output with wrong
shading normals is rejected by the new check. Face smoothing is configured before
custom-normal encoding; comparison renders retain the previous skin shading.

Banded iron cuirass and iron boots are rendered from final exported NIF/DDS in
rest, walk and sword-attack states, with separate body-only/boots-only states.
Iron gauntlets are also converted in an isolated copy and rendered in actual
sword-attack frames, including the hand/sword close-up. Equipment has valid
partitions, private skeleton bones, up to four normalized skin weights, private
texture paths and identical low/high weight variants. Embedded source skin is
removed and exposed target skin is checked against the original target body.

These checks do not establish universal fit quality for every avatar/equipment
combination. Individual input previews and game equip/remove behavior remain
distinct checks. The generated README explains removing original VRM wardrobe
layers before wearing game equipment and installing the separate armor patch.
Physics, first-person/player-race use and helmet/other-master inputs are outside
this fitting implementation.

## 0.4.1 package coexistence (2026-10-11)

The shared root settings JSON caused a file conflict when two generated followers
were installed together. Settings and documentation now live under each MOD ID's
private path. A regression test repackages two old-layout outputs, checks every
installed ZIP path case-insensitively, reads settings back, verifies CRC/manifests,
and requires game-file bytes to remain unchanged. This test is included in CI.

The two previously delivered follower packages were also repackaged locally.
Their complete ZIP file lists have no shared paths. All ESP, NIF and texture bytes
match the previous delivered archives. Source VRMs and original ZIPs were retained.

Twenty Python tests and Ruff pass. This metadata-only fix does not provide new
gameplay or wardrobe verification.

## 0.4.0 wardrobe verification (2026-10-11)

Nineteen Python tests pass locally, including source-hash binding, exact mesh
coverage, duplicate/reserved/conflicting slot rejection, independent skin and
garment records, stats/default-outfit/inventory linkage, and secondary-rig
matching by name, rest position, limb direction and uniqueness. Ruff passes.

A real local humanoid VRM with separate body, underwear, face/hair and clothing
was exercised through the actual wizard in a dedicated headless Chrome profile:

- Enable wardrobe mode, review roles, split/combine garments and edit item stats.
- Render front/back source classification previews with garments removed.
- Navigate back, export settings, import those settings through the file input.
- Start actual conversion from the button, load output previews and save the ZIP.
- Check desktop and 390-pixel mobile layouts, with no horizontal overflow or
  browser JavaScript error.

The fixed-appearance Sophie journey also passed through real conversion,
output previews and ZIP download with wardrobe mode disabled. The 0.3 results
below remain historical evidence rather than new game acceptance.

The wardrobe output is read back component by component. Each NIF is compared
against its own source nodes, not only the assembled point cloud. Partitions
match the assigned slot; all components use the delivered skeleton; triangle
totals, texture paths, weight limits, private record references, permanent skin
and initial clothing are checked. Source materials are copied for the independent
comparison so NIF shader normalization cannot destroy source alpha graphs.
The exported opaque shaders use alpha 1 regardless of an ignored glTF factor.

The actual output NIFs and decoded DDS are rendered clothed and in underwear,
with vanilla walk/attack clips and individual garment-removal states. Secondary
clothing/hair bones are matched against the primary humanoid using actual rest
geometry, retaining their offsets. Ambiguous matches are rejected; unrelated
accessory rigs are not assumed to be humanoid copies. The assembled renders
are inspected before handoff.

Private avatar names, node layouts, hashes, model-specific results and images
remain local in ignored build/audit directories. They are not published as test
fixtures or documents. The public test accepts a user-supplied local VRM.

### Remaining game checks for 0.4

Install the generated ZIP on a test save, enable the ESP and restart Skyrim.
Check placement/recruitment, then remove/re-equip each original garment using
the generated README's FormID commands. Check that body/underwear/face/hair remain.
Verify default outfit behavior, normal follower inventory dialogue, dismissal,
and save/reload. The offline previews do not verify these runtime transitions.

Existing Skyrim armor fitting and independent cloth/hair physics are not
implemented. Inventory/dropped-item models use the base game's generic clothing
model; worn models use the converted VRM garment meshes.

## 0.3.0 verification history

Checked on 2026-10-11, Windows, Python 3.11, Blender 4.5.12, local Skyrim SE assets.

## Verified journey

The browser E2E used a separate headless Chrome profile and the actual local
wizard. It uploaded a real VRM, changed NPC/MOD names and voice, switched combat
presets, set manual stats/skills, selected a Perk and spell, navigated back without
losing selections, downloaded the settings JSON, pressed the conversion button,
loaded the output previews, and downloaded the generated MOD ZIP. No mock
conversion was used. A second run built the delivered default Sophie profile.
The desktop and 390-pixel-wide result screens were rendered and visually checked;
there was no horizontal overflow or unhandled browser JavaScript error.

Fourteen Python tests pass, including format bounds, VRM 0/1/thumb semantics,
rigid rotation/palm alignment, configuration rejection/roundtrip, and actual
Skyrim.esm-based follower integration tests. Ruff 0.11.13 passes.

The integration checks parse the generated ESP and verify:

- PotentialFollowerFaction rank 0, CurrentFollowerFaction rank -1.
- Unique NPC, Ally RELA to Player; voice from the actual VoicesFollowerAll list.
- Private race/skeleton references and consistent body armor/addon/outfit references.
- Persistent ACHR under the Temple of Kynareth's real interior block/sub-block and
  persistent-reference group. The existing center marker supplies position.
- Gender, fixed/following levels, stat offsets, manual skills, protection, AI,
  class/style, Perk/rank, spells, weapon/ammunition, height and placement offsets.
- Distinct Editor IDs and asset paths for two different MOD IDs.
- Correct TES4 record/group count; only the intended temple CELL is overridden.

## Model checks

| Input | Result |
| --- | --- |
| Sophie, VRM 1 | 18 output shapes, 220,594 triangles, 10 DDS, 151 skeleton nodes |
| Official UniVRM AliciaSolid, VRM 0 | 20 output shapes, 31,798 triangles, 7 DDS, 151 skeleton nodes |
| AliciaSolid with male settings | Full pipeline, male skeleton, MaleNord voice, male NPC template and male walk clip pass |

The [official AliciaSolid input](https://github.com/vrm-c/UniVRM/blob/master/Tests/Models/Alicia_vrm-0.51/AliciaSolid_vrm-0.51.vrm)
contains expression morphs and BLEND materials. It is a local test input and is
not redistributed with the project. Alpha and depth-write settings are retained;
the exported model/texture previews were checked in the same pose as the source.

Every shape fits the NIF vertex-index limit. Weights have 1–4 influences and sum
to 1 within tolerance. All texture references resolve inside that MOD's namespace.
Source triangles are preserved. Static vertices are compared in both directions
against an independent Blender evaluation of the original posed VRM. The
delivered Sophie profile's maximum distance is 0.0000352481 game units (limit 0.001).

Animation-controlled skeleton local transforms remain unchanged. Rigid parent
offsets retain all eight upper/lower arm/leg segment lengths across the actual
35-frame walk and 40-frame attack clips. This test does not evaluate runtime
foot IK or ragdoll simulation.

The actual exported NIF and decoded DDS were rendered for the source comparison,
rest pose, four walk frames, four attack frames with steel-sword geometry, and a
hand close-up. Images were visually checked. The sword material is a neutral
metal preview; these are standard animation tests rather than every possible
selected weapon/class animation.

## Delivered Sophie test MOD

- File: `SophieFollower-VRM2Skyrim-0.3.0.zip`
- Bytes: 79,807,039
- SHA256: `3e463b38041e8db7558787436088d2056d05d7626ac89270c3e80af790310706`
- Plugin: `SophieFollower.esp`
- Settings: female / FemaleEvenToned / one-handed warrior / protected /
  player-level multiplier 1 / levels 5–80 / base health-magicka-stamina 200-100-150.
- Perks/spells: none in this default profile; configurable in the wizard.
- Spawn: `WhiterunTempleofKynareth`, using its existing center marker.

ZIP CRC, SHA256, and byte-for-byte correspondence between the archive and the
validated output folder pass. Regenerating the plugin with the final stat-offset
writer produced exactly the same plugin bytes. Original VRM bytes are unchanged.
Inputs, game assets, generated MODs and screenshots remain local under ignored
directories; only tool source and documentation belong in the repository.

## Game boundary

On 2026-10-11 the user reported that verification of the delivered 0.3 Sophie
follower was OK. This is retained as user-confirmed acceptance of that follower,
in addition to the earlier 0.2 appearance confirmation. It does not establish
acceptance of other profiles or the 0.4 wardrobe behavior.

Ragdoll fitting, facial animation and hair physics are not implemented.
Selected equipment fitting is described in the 0.5 section above. The temple
CELL retains master metadata and can need a
load-order compatibility patch with other mods that edit that cell.
`game_verified` stays false for new follower builds until the relevant game
journey is confirmed.
