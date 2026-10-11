# Skyrim record and skeleton sources

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
