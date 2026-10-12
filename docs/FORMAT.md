# Skyrim record and skeleton sources

## 0.7.0 equipment identities and private models

The official catalog reads installed base/DLC/Creation masters, resolving every
disk FormID through that file's MAST array, including ESL files. Saved equipment
identities use `owner-plugin:local-24-bit-id`; catalog indices and runtime load
order are not persistent identities. Female actors can use the shared male model
when the addon has no female model. Human addons are selected separately from
beast-specific addons. An item may have several humanoid addons, and enchanted
variants share the same fitted addon geometry.

The follower keeps its Skyrim-only master layout and existing saved local IDs.
Fitted private ARMA records begin at `0x1000`, one per unique source addon. The
combined armor patch adds them to the original ARMO, remapping all references,
VMAD object properties and alternate texture sets into its master order. Original
statistics, enchantments, keywords, names and original-race addons are retained.
Footstep references and all five equipment/visibility lists are overridden in the
combined patch, which owns the required DLC/Creation dependencies.

Permanent VRM face/hair/accessory geometry shares one slot-60 addon. Full,
face-hidden, hair-hidden and both-hidden Skin ARMO records use local IDs
`0x801/0x852/0x853/0x854`, with visibility FLSTs `0x855/0x856` and optional variant
addons `0x860..0x862`. Empty visibility variants omit that addon. SKSE's
ActorBase.SetSkin and Actor.QueueNiNodeUpdate switch geometry without equipping a
head-cover item or restoring native FaceGen. Equip/load/NiNode events reconcile
the selected private skin; unchanged skin never queues another refresh.

Original equipment uses its native biped mask. Helmet partitions 130/131/142 map
to biped layers 30/31/42. Unskinned shields use the custom skeleton's SHIELD
attachment. Alternate texture sets are applied per shape; missing optional
native texture maps are explicitly omitted and recorded in the fitting plan.

Finishing overrides store vertex positions and normals by avatar SHA256 plus a
source key derived from the addon identity, sex, reference body/skeleton and
source NIF. Import rejects topology/UV/name changes and changes to original
skin. NIF and Blender UV origins are reconciled when reusing the edit. Explicit
partition names avoid the exporter's Blender duplicate-suffix truncation.
Failed imports restore the prior meshes, saved override and archives.

The converter reads the user's installed Skyrim.esm and BSAs. No game assets or
VRM inputs are part of this repository. Editor IDs are resolved against that
master rather than guessed FormIDs.

Since 0.4.1, generated documentation and reproducible settings use
`vrm2skyrim/<lowercase mod_id>/README.txt` and `settings.json`. The former root
`README.txt` and `VRM2Skyrim-settings.json` are removed when repackaging an older
output. These metadata files are not read during gameplay. Coexistence checks
compare all installed ZIP paths case-insensitively, not just game assets.

The binary field layouts follow [xEdit's TES5 definitions](https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.5/Core/wbDefinitionsTES5.pas).

- NPC ACBS: uint32 flags; signed int16 magicka/stamina offsets; level, min/max,
  speed; disposition; template flags; signed int16 health offset; bleedout.
  Unique=0x20, Female=1, Essential=2, Protected=0x800, AutoCalc=0x10, PCLevelMult=0x80.
  Health/magicka/stamina settings represent pre-growth base values; their offsets
  subtract the copied race's starting values. With PCLevelMult or AutoCalc enabled,
  class/level growth is still applied by the game. DNAM is not a guarantee of the
  final displayed actor health. See the patcher author's
  [health calculation documentation](https://www.nexusmods.com/skyrimspecialedition/articles/6618).
- NPC AIDT: aggression, confidence, energy, responsibility, mood, assistance.
  Assistance=2 is Helps Friends and Allies.
- NPC DNAM: 18 uint8 skill values, 18 uint8 offsets, uint16 health/magicka/stamina,
  then the preserved remainder. Manual skill values require AutoCalc=false.
- NPC PRKR: perk FormID, uint8 zero-based rank, three padding bytes.
- RELA DATA: parent/child FormIDs, uint16 rank enum, uint8 unknown/flags, association.
  Ally=1 in this enum. This differs from Papyrus relationship rank numbering.
- CurrentFollowerFaction rank=-1 and PotentialFollowerFaction rank=0, with an Ally
  player relationship, use Skyrim's standard follower system. Supported voice
  choices come directly from VoicesFollowerAll in the installed master.
- ACHR is persistent and grouped under CELL→interior block→sub-block→cell children
  (6)→persistent references (8). Interior block labels are copied from the actual
  master cell's ancestry. The temple's existing center marker supplies position.
- The parent CELL record is a copy of the master record; its original fields are
  retained. It can conflict with other plugins that edit the same cell's lighting
  or metadata; resolve such overrides through ordinary mod load-order/patching.

The skeleton keeps animation-controlled local transforms and adds unanimated
rigid parent nodes. This follows the proxy-node mechanism described in the
[Beyond Skyrim animation skeleton tutorial](https://wiki.beyondskyrim.org/wiki/Arcane_University:Editing_Animation_Skeletons).
The mesh is posed using rotations, with no per-limb fitting scale, and rebound
to the custom skeleton. The static result is checked against an independent
evaluation of the original VRM in the same pose.

Input node names are normalized on a temporary GLB, preventing Blender's duplicate
name/truncation behavior from changing semantic bone mapping. VRM 0 thumb joints
are mapped to the VRM 1 naming convention. Facing is derived from left/right
humanoid joints. Large shapes are split by faces without decimation; each part
keeps UV/deform data and the original computed corner normals.

OPAQUE, MASK and BLEND materials are exported with the appropriate NiAlphaProperty.
DDS files retain alpha. MToon lighting, physics and expression animation are not
reproduced. Existing expression defaults are baked into the fixed appearance.

Native tool dependencies: [PyNifly](https://github.com/BadDogSkyrim/PyNifly) V29.1.0
(GPL-3.0) and [DirectXTex](https://github.com/microsoft/DirectXTex) may2026 (MIT).
The bootstrap checks the pinned download hashes and installs them locally.

## Wardrobe mode (0.4)

`appearance.json` lists each NIF's source node indices, role, slot and output
shapes. Body, permanent underwear and fixed face/hair use separate Skin ARMA
records at slots 32, 52 and 60. Wearable original garments use distinct layer
slots 44–49/53–59. Each garment gets ARMO/ARMA records, a name, clothing/light/heavy
type, integer hundredths of armor rating, weight and value. Initial garments go
into OTFT; other garments go into NPC CNTO. All records use the same private race
and all geometry uses the same delivered skeleton. Inventory/dropped models
reference the master game's generic farm-clothing model; its assets are not copied.

Primary humanoid joints and secondary rig candidates are compared in model
space, after all original parent transforms. Candidate names alone are not
enough: rest distances, limb directions, distinct rig ownership and uniqueness
are checked. The primary world-space pose delta is applied to secondary joints,
retaining their original rest offset. Descendants inherit their matched anchor.
This is static retargeting into a shared game skeleton, not cloth/hair simulation.

Source comparison materials are independent copies of the imported glTF graph.
NIF shader normalization must not make transparent source detail planes opaque.
OPAQUE ignores the glTF base-color alpha factor; BLEND/MASK retain the applicable
alpha behavior. Component validation compares against the corresponding source
node vertex cloud and requires each shape's NIF partition to equal its assigned
slot. The source hash binds saved classification to the actual input VRM.

## Selected equipment fitting (0.5)

### Native head hiding correction (0.5.1)

Wardrobe Skin slot 60 does not hide the head generated from NPC/RACE head data.
The engine combines **worn ARMO** body masks to hide native head/hair; Skin alone
is not a worn outfit item. See the author's reverse-engineered
[equipment pipeline](https://github.com/DavidJCobb/skyrim-outfit-system/blob/master/skse-plugin/SkyrimOutfitSystem/Patches/OverridePlayerSkinning.cpp#L49-L57).
Unlike the fixed mode's equipped Appearance armor, 0.4/0.5.0 only equipped the
garments. Inherited vanilla head parts could therefore render over the VRM face.

Local ARMO 0x80B is a non-playable, zero-value/weight/rating, meshless head cover
in the default OTFT. It occupies native head/hair/circlet/ears slots 30/31/41/42/43
only, with no Armature or world model. It leaves body/clothing and VRM Skin slot
60 alone. Existing Skin records and all exported geometry remain unchanged.
Native head data is retained for engine compatibility, but hidden by worn flags.
Normal garment removal leaves the head cover equipped. `unequipall`, changing
the entire default outfit, and external equipment-management mods can remove it;
equipping the cover again restores its flags. Headgear fitting is not supported.

`validate_head_visibility` reads actual OTFT/ARMO masks separately from NIF checks.
It rejects the old outputs, checks the hidden cover and its zero stats, prevents
hiding VRM slot 60, and checks fixed mode too. This is binary-configuration
validation, not evidence of the game engine's rendered result.

`fit_armors` is a list of up to 64 distinct Skyrim.esm ARMO Editor IDs. It requires
wardrobe mode and a complete independent body. The source is the game's original
BSA mesh/texture, with a humanoid ARMA at body, hands or feet. Reference-skeleton
hierarchy takes precedence over flattened skin-bone lists in mesh NIFs. A weighted
bone-segment field aligns equipment to target lengths and widths, followed by a
local body-surface correction. Target skin is not deformed by this field.

Original skin triangles are partitioned by the conformed reference body's regions:
torso=32/34/38, hands=33, feet=37. Original triangle coverage is read back exactly;
split vertices retain positions, UVs, normals and weights. Embedded vanilla skin
is removed from equipment. Original target skin is included at exposed regions.
Native equipment priorities preserve calf/forearm hiding when combining pieces.
Auxiliary armor bones without a humanoid ancestor use the source skin's nearest
weights; exported equipment receives the target body's weights. Both weight
variants retain the same target geometry. Output skin and fitted NIFs share the
original custom skeleton and their textures use private per-MOD paths.

Private fitted ARMA records start at local 0x880. The follower ESP does not override
the original ARMO. `vrm2skyrim/<mod_id>/armor-fitting.json` publishes the local
manifest to the user's installed Data folder. The separate combined armor patch
has Skyrim.esm and the chosen follower ESPs as masters, appends their ARMA FormIDs
to original ARMO Armature lists, and retains stats and original addons. Localized
names/descriptions are resolved into inline strings for the unlocalized patch.
Only one combined patch should be active. Installed metadata and completed wizard
outputs provide trusted candidates; the API accepts handles, not file paths.

The preview renderer uses the complete original skin as its common import rig:
unweighted helper-bone orientation can vary between independently imported parts.
Weighted bone rest poses are checked before all components animate on that rig.
Game equip/remove behavior and compatibility with other armor overrides remain
separate from offline geometry/binary/render verification.


## 0.6.0 head and equipment ownership

The 0.5.1 cover is retired: AFT can unequip/remove it. DATA flags at byte 32 of
RACE disable bit 1 (0x2) FaceGen Head, as defined in xEdit and
[CommonLibSSE](https://ryan.commonlib.dev/TESRace_8h_source.html).
VRM head geometry remains in Skin. Private HDPT 0x80C / FLST 0x80D replace all
human head references; generated meshless BSFadeNode head and FaceGeom assets
provide an empty fallback. Old cover 0x80B remains an inert FormID with mask 0
for saved inventory references, never initial equipment. Head parts and shapes
cannot be restored by changing the default outfit or stripping equipment.

Wardrobe OTFT is empty and all garments are ordinary CNTO items. Seven FLSTs
at 0x840-0x846 bind InitialItems, Body/Hands/FeetClothes and Body/Hands/FeetEquipment
to a private Actor VMAD script. Garments have optional equipment_group values
body/hands/feet/accessory; omitted old settings derive an editable suggestion
from their names. Gear categories use actual source ARMO slot 32/33/37. Only
selected fitted game items participate. The source and compiled PEX are under
runtime/. Per-mod PEX string-table renaming preserves every object/function index
and instruction. Header metadata is sanitized. Class name, script path and VMAD
bindings are private; no common runtime path causes follower ZIP collisions.

OnInit equips configured inventory items once unless already a player teammate.
OnObjectEquipped only unequips that group's conflicting items, ignoring delayed
events for already-removed items. In 0.6.1 fitted gear wins in either event order:
a re-equipped garment removes matching clothes, never fitted gear. Original
clothes can be worn after the corresponding gear is removed. OnLoad repairs overlapping current equipment
without restoring clothes or changing any outfit. AFT retains ownership of its
sets and inventory. Template PEX is Skyrim 3.2, built with Orvid/Caprica v0.3.0
against the user's Actor/ObjectReference/FormList declarations; missing unused
type declarations are compile-only and are not distributed. Compiler archive
SHA256: 0037e54cf3a1021e976278d9a637e8ae541aaf9ebeb8d274b6c2cfe32f4ee559.

Optional garment `item_kind` is body/legs/hands/feet/cloak/backpack/accessory.
Omitted old settings infer usage from the name. It controls native semantic
keywords, independently of equipment_group and the render/equip slot. Clothing
gets ArmorClothing + VendorItemClothing and ClothingBody/Hands/Feet where relevant;
armor gets ArmorLight/Heavy + VendorItemArmor and ArmorCuirass/Gauntlets/Boots.
Legwear shares the native body keyword because Skyrim has no separate pants
classification. SkyUI subtype follows its part-mask precedence, not these usage
keywords ([upstream InventoryDataSetter](https://github.com/schlangster/skyui/blob/master/src/ItemMenus/InventoryDataSetter.as)).
The user's UI labels layer 46 as cloak and 47 as backpack. The wizard explains
this convention, prefers 53-59/44/45/48/49 for ordinary split clothes, and keeps
imported explicit slots unchanged. Selecting a different slot rebuilds both
records and NIF partitions through the normal conversion pipeline.
The test VM reads the real PEX format using the author's Caprica/pex schema;
its mocked native calls establish code behavior, not actual game compatibility.

## 0.6.2 material face culling

Original glTF materials retain `doubleSided` (default false). Do not force the
Skyrim DOUBLE_SIDED shader flag on opaque, masked or blended materials. Their
alpha modes and MToon depth-write choices remain independent. See the
[glTF double-sided specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#double-sided).
`nif_materials.apply_alpha` also enforces culling and reads the saved NIF back.
Appearance shape metadata records source sidedness; final validation rejects
a mismatching native flag where that metadata is present.

This corrects eye strips caused by back-facing eyelash geometry covering the
front-facing sclera. Default morphs and texture transparency are unchanged.
Cycles previews use an explicit Geometry.Backfacing transparent branch for
single-sided materials because viewport culling alone does not govern Cycles.
The branch wraps the current surface shader, preserving its alpha handling;
explicit double-sided materials are left intact. Source previews use stable
material IDs, and exported-NIF previews follow native material flags.
