# Finger joints under animation

## Finding (2026-11-02)

Every VRM's fingers looked long, thin and jointless in game, including
VRChat-derived avatars with sound hand rigs. The cause was the custom skeleton.

Skyrim HKX writes each animated bone's local translation on every frame. The
offset nodes in `custom_skeleton.py` assumed those translations equal the source
NIF's, and that holds for every bone of `skeleton.nif`. In `skeleton_female.nif`
29 of the 30 finger bones are about 15% shorter than the HKX reference; all other
translations and all rotations match, and the finger tracks equal the reference
in every sampled animation. Each female finger joint therefore moved out by the
difference: about 1.66 game units (2.4 cm) at the fingertip of a NIF-scale hand,
regardless of the avatar. The skin stayed rigid inside each segment, so only
the regions between bones stretched.

`verify_animation` measured limbs only, which is why it passed.

## Contract

Custom joints are defined by what animation writes: the offset satisfies
`P @ V = C` for the HKX reference translation. The private skeleton stores that
translation on the bone, so the file's rest pose is still the custom pose and
skin binds, fitting and previews need no change. Male output and all non-finger
bones produce the same offsets as before.

`verify_animation` covers every finger segment. Hand node scale is held at the
NIF value there: it is uniform, so it cannot stretch a finger against its width.

Not yet verified in game. Whether the engine keeps the hand's 0.85 node scale
during animation was not determined; the proportions above do not depend on it,
the overall hand size does.
