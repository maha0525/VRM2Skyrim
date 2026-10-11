# VRM2Skyrim verification

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
