# VRM-only toon shading prototype

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
Exclude unskinned and True PBR permutations. Pin the entire installed
Lighting.hlsl SHA256: the DLL's 1.9.0.0 version alone did not identify its
actual shader source. Carry VRM 0/1 shade/lit color ratios and shadow-edge
parameters; outlines, shade textures, matcaps and rim light remain outside
this prototype.

Compile 16 original/patched permutation pairs, and render the actual
compiled Community Shaders pixel shader against the real NIF/DDS output
in an offscreen Direct3D 11 harness. Compare unmarked, marker-only fallback
and zero-light images byte for byte. The full Aifi source conversion must
also pass geometry, physics, material and 75-frame animation readback.
