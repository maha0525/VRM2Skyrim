# Skyrim record and skeleton sources

The converter reads the user's installed Skyrim.esm and BSAs. No game assets or
VRM inputs are part of this repository. Editor IDs are resolved against that
master rather than guessed FormIDs.

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
