# VRM-only toon shading prototype

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
