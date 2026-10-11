# VRM2Skyrim 0.3.0 verification

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

The user confirmed the original 0.2 Sophie's appearance inside Skyrim. This is
retained as an appearance confirmation, not treated as acceptance of the new
follower behavior. The following 0.3 checks are still required in Skyrim:

1. Enable the generated ESP, restart Skyrim, and enter the Temple of Kynareth.
2. Find Sophie and verify the standard recruitment dialogue appears.
3. Recruit, follow, wait, dismiss, then recruit again.
4. Check behavior/stats/spells with the chosen profile and the installed mod set.

Ragdoll fitting, facial animation, hair physics and armor appearance replacement
are not implemented. The temple CELL retains master metadata and can need a
load-order compatibility patch with other mods that edit that cell.
`game_verified` stays false for new follower builds until the relevant game
journey is confirmed.
