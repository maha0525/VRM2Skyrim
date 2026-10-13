# Direct3D-compatible DDS dimensions

The user reported Engine Fixes texture warnings on exit. The actual log
recorded three failed attempts to load Erys's tex_011_metal_1_2.dds. The file
in Data matched the generated 0.8.0 ZIP: a 2x2 BC7_UNORM DDS. Creating a
hardware D3D11 texture from its mip payloads reproduced E_INVALIDARG.
Uncompressed RGBA8 at the original 2x2 size succeeded with identical pixels;
4x4 BC7 also succeeded. Existing checks only verified files and CPU decoding.

Select BC7 only when both top-level image dimensions are multiples of four.
Otherwise use uncompressed RGBA8, preserving the original dimensions, pixels,
UVs, and alpha. Apply this centrally in convert_textures so follower creation,
headgear previews, and all other callers use the same behavior. Do not add an
Erys-specific workaround, resample the user's image, suppress Engine Fixes,
or change NPC/item records or save data.

Read the produced DDS header and check dimensions, compression alignment,
format, and mip payload size. Validate referenced DDSs before decoding them
for previews, so old/corrupt incompatible outputs cannot pass a full build.
Include format/dimension details in logs and validation reports.

Verify aligned and unaligned source dimensions, colors/alpha, and mip chains
with the actual pinned texconv; reject a CPU-decodable 2x2 BC7 regression
fixture. Test emitted files with D3D11 and repackage the existing Erys follower
without changing its ESP, meshes, item IDs, or skeleton. Keep old outputs as
backups. Make this a stable 0.8.1 correction independent of FSMP development.

Evidence: build/texture-load/REPORT.md and d3d-results.json (local only).
References:
- https://github.com/aers/EngineFixesSkyrim64/blob/master/src/fixes/texture_load_crash.h
- https://learn.microsoft.com/en-us/windows/win32/api/d3d11/nf-d3d11-id3d11device-createtexture2d
