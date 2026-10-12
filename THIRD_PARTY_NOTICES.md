# Licensing, dependencies, and generated assets

## Original VRM2Skyrim code

Original VRM2Skyrim source code and documentation are licensed under the
[MIT License](LICENSE), copyright 2026 maha0525 and VRM2Skyrim contributors.
Keep that copyright and permission notice when redistributing copies or
substantial portions of this original code.

This grant does not relicense third-party software, input avatars, Skyrim
assets, or assets from other MODs. Their respective rights holders and licenses
continue to apply. A generated package can contain material with several
different licenses; the repository's MIT license is not a blanket license for
everything in that package.

## External software

Third-party dependencies are obtained separately by Setup or installed by the
user. `dependencies/`, `reference/`, and `build/` are excluded from this source
repository. Preserve the upstream licenses and copyright notices when
redistributing any of these components, including notices for libraries
bundled inside their binaries or Python wheels.

| Component | Version used by this project | License and source |
| --- | --- | --- |
| PyNifly | V29.1.0 | [GPL-3.0 license](https://github.com/BadDogSkyrim/PyNifly/blob/V29.1.0/LICENSE); [corresponding source](https://github.com/BadDogSkyrim/PyNifly/tree/V29.1.0) |
| DirectXTex / texconv | may2026 | [MIT license](https://github.com/microsoft/DirectXTex/blob/may2026/LICENSE); [source](https://github.com/microsoft/DirectXTex/tree/may2026) |
| NumPy | 1.26.4 | [BSD-3-Clause](https://github.com/numpy/numpy/blob/v1.26.4/LICENSE.txt) |
| SciPy | 1.16.0 | [BSD-3-Clause](https://github.com/scipy/scipy/blob/v1.16.0/LICENSE.txt) |
| Pillow | 10.4.0 | [HPND](https://github.com/python-pillow/Pillow/blob/10.4.0/LICENSE) |
| python-lz4 | 4.4.5 | [BSD-3-Clause](https://github.com/python-lz4/python-lz4/blob/v4.4.5/LICENSE) |
| Playwright (development tests) | 1.62.1 | [Apache-2.0](https://github.com/microsoft/playwright/blob/v1.62.1/LICENSE) |

Blender is installed separately; see its [licensing information](https://www.blender.org/about/license/).
SKSE64 and optional tools such as Outfit Studio, BodySlide, Vortex, and MO2
are separate projects, not relicensed by VRM2Skyrim. Obtain them from their
authors and follow their own terms.

### PyNifly and redistribution of an assembled converter

VRM2Skyrim imports PyNifly's Python modules and uses its native library, in
addition to invoking its Blender operators. This is direct library integration,
not just conversion through an unrelated executable.

MIT is GPL-compatible, so the original VRM2Skyrim modules can remain available
under MIT. However, an assembled converter distributed together with PyNifly
must comply with GPL-3.0 for the combined work. Do not label that combined
distribution as MIT-only or remove PyNifly's license notices. Distributing
PyNifly separately does not by itself remove the obligations of a combined
work.

When distributing that combination, supply the GPL license and required
notices, retain the MIT notices for the original modules, and provide the
corresponding source under the GPL's distribution requirements. For a binary
bundle, this includes the relevant PyNifly/native-library source and source
needed to build and modify the combined converter; an arbitrary link to a
different upstream version is not a substitute. Preserve any additional
upstream component notices as well. The exact license text governs these
obligations.

References: [PyNifly V29.1.0 license](https://github.com/BadDogSkyrim/PyNifly/blob/V29.1.0/LICENSE),
[GNU FAQ on GPL libraries](https://www.gnu.org/licenses/gpl-faq.en.html#IfLibraryIsGPL),
[GNU FAQ on interpreted programs and bindings](https://www.gnu.org/licenses/gpl-faq.en.html#IfInterpreterIsGPL).

## Avatars, game assets, and generated follower MODs

The repository does not include input VRM models or extracted Skyrim assets.
Conversion does not transfer ownership or grant additional redistribution
rights:

- Follow the avatar author's terms and the input VRM's license metadata for
  use, modification, attribution, and redistribution. Being able to select a
  model in the wizard does not mean its author permits distribution of a MOD.
- Skyrim skeletons, meshes, textures, and other game-derived content remain
  subject to Bethesda's applicable terms. This project grants no permission
  to redistribute those assets.
- Equipment replacers, UNP/CBBE-related assets, and other third-party MOD
  resources keep their authors' permissions and attribution requirements.
- Original VRM2Skyrim runtime scripts retain the project's MIT license. If
  you redistribute those scripts, include the MIT copyright and permission
  notice with your MOD. This does not extend MIT to avatar or game assets
  packaged alongside them.

Follower ZIPs and Outfit Studio editing kits can contain transformed avatar
assets and game-derived resources. Check the terms for each included resource
before sharing either kind of archive. Generated settings and readmes do not
override those terms.

Using a GPL tool does not automatically place its output assets under GPL;
GPL-3.0 section 2 applies to output only when its content itself constitutes
a covered work. See the [GPL text](https://github.com/BadDogSkyrim/PyNifly/blob/V29.1.0/LICENSE).
Model and game permissions must still be respected independently.
