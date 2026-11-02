# Avatar placement on the actor origin

## User intent (2026-11-03)

DeepSeek-chan stretched her neck forward, bent at the waist with only her legs
stepping ahead, and once turned fully invisible. No other follower did this. Her
VRM's `root` node is placed 0.275 m forward (and 0.288 m up) of the scene origin,
so the hips, head and feet all stand about 27 cm in front of it. The converter
oriented and scaled the VRM but kept that translation: the custom skeleton put
`NPC Pelvis [Pelv]` 19.2 units in front of `NPC COM [COM ]` and `NPC Spine [Spn0]`
24.9 units in front of it. Erys's pelvis sits on the COM.

Skyrim's animations turn and bend the body by rotating the COM and the actor
around the origin. A body standing in front of that pivot sweeps through wide arcs
when the COM pitches or turns, which fits the neck and waist symptoms. The
invisibility may come from the body leaving the bounds the engine culls with; that
was not checked.

## Rule

`convert_blender.py` moves the avatar horizontally so the hips stand over the origin,
right after deriving the facing. The translation is folded into `orient`, which every
source position, mesh, physics bone, spring tail and collider goes through, so their
relative placement and the height are unchanged. A VRM already centred moves by its
small remaining offset; the log line reports the distance.

## Verification

Converted DeepSeek-chan, Lucia and AnimalKawaii_01_Kuro through the whole pipeline
and compared the pelvis offset from the COM in `skeleton.json` before and after.
Whether the in-game neck, waist and invisibility symptoms are gone has to be seen
in game.
