# VRM2Skyrim Toon

[English](#english) | [日本語](#日本語)

## 日本語

トゥーン描画は初期ONで、STEP 01から切り替えられます。元VRMのMToon材質に設定された影色・MatCap・リムライト・輪郭線・ノーマルマップを、顔・身体・髪・衣服に反映します。背景、通常NPC、体型合わせしたSkyrim装備は従来の描画を使います。Skyrim向けの照明調整を含みます。

### 対応する表現

- 元の影テクスチャ・影色・明暗の境界・環境光設定を使います。強い光での白飛びと、Screen Space GIから後付けされるAO・間接光を対象VRMだけ抑えます。
- MatCap、リムライトの色・強さ・マスク・照明への追従、ノーマルマップの強さを材質ごとに引き継ぎます。設定されていない効果は加えません。
- 輪郭線は実寸幅（worldCoordinates）と幅マスクに対応します。衣服や髪と一緒に着脱・表示切替・揺れへ追従します。画面比率で幅を指定するscreenCoordinatesは未対応で、変換時に通知します。
- 画像の解像度とRepeat / Clamp to Edge / Mirrored Repeatを保ちます。元の形状・法線・UV・スキンは保持し、輪郭線だけ専用の形状を加えます。衝突計算には加えません。
- 元の発光テクスチャとUVアニメーションは未対応です。

### 導入

**トゥーン描画には、トゥーン描画を有効にして出力したフォロワーと、トゥーン描画用シェーダーのZIP（`VRM2Skyrim-Toon-Shader-0.13.0.zip`）の両方が必要です。** シェーダーのZIPは、NexusのBottled Shaders **1.0.22** として導入されるCommunity Shaders（DLLの版は1.9.0.0）用です。同じ1.9.0.0を名乗るBottled Shaders 1.0.4などの他のリリースでは、シェーダーの中身が異なるため使えません。配布された材質更新パッチがある場合は、該当するフォロワーを再出力する代わりに使えます。旧8x4マーカー、顔専用の試作4、全身対応の試作5の材質も、新しいシェーダーで使えます。

1. Skyrimを終了します。
2. 更新した本体のSTEP 01の「トゥーン描画」を有効にして、フォロワーを再出力してVortex / MO2へ導入します。同じMOD IDの旧版を置き換えます。材質更新パッチを使う場合は元フォロワーより優先します。
3. ウィザードの「トゥーン描画用シェーダーをダウンロード」ボタン（STEP 01と変換結果の画面にあります）で `VRM2Skyrim-Toon-Shader-0.13.0.zip` を保存します。VRM2Skyrimのフォルダ内の `toon-shader` フォルダにある同じZIPを使っても構いません。以前のシェーダー試作MODと材質更新パッチを無効化し、このZIPをVortex / MO2で導入します。Community Shadersより優先させ、VortexではDeployします。
4. ゲーム終了中に実際の `Data/ShaderCache` を別名へ退避します（例：`ShaderCache-before-toon`）。MO2でOverwriteへ出している場合は、そのキャッシュを退避します。`Data/Shaders` は移動しません。
5. SKSEから起動し、コンパイル終了後に確認します。Screen Space GIは有効のまま使えます。初回はコンパイルに時間がかかります。

ウィザードは、ゲームフォルダの `Data/Shaders/Lighting.hlsl` と `Data/Shaders/DeferredCompositeCS.hlsl` の中身を照合して、ダウンロードボタンの横に状況を表示します。Bottled Shaders 1.0.22の元のファイルなら、次にZIPを導入するよう案内します。このZIPのファイルなら導入済みと表示します。どちらでもない場合は、他のリリースでは描画が崩れる場合があるという注意を表示します。ファイルが見つからない場合（MO2ではシェーダーがMO2のmodsフォルダにあります）は、確認できなかったことと対象のリリースを表示します。注意が出てもトゥーン描画は選べます。

通常のBlenderプレビューはこのシェーダーを使いません。

Bottled Shaders 1.0.4用の試作6シェーダーは、1.0.22では使えません。Bottled Shaders 1.0.22へ更新したら、試作6シェーダーを無効化してこのZIPへ入れ替え、キャッシュを退避します。フォロワーの材質パッチはそのまま使えます。

戻す場合は、材質パッチとシェーダーを両方とも以前の組み合わせへ戻し、Deploy・キャッシュ退避・SKSE再起動を行います。Community Shaders本体を更新する場合は、先にトゥーン描画用シェーダーのZIPを無効化します。

### ライセンス

VRM2Skyrim本体はMITライセンスです。トゥーン描画用シェーダーのZIPには、VRM2Skyrimが2026-10-28にトゥーン描画のために変更したCommunity Shadersの `Lighting.hlsl` と `DeferredCompositeCS.hlsl` が入っています。このため、ZIPの中身（同梱の `VRM2Skyrim/*.hlsli` を含む）は、Community ShadersのModding ExceptionとGPL-3.0 Linking Exceptionを伴うGPL-3.0で配布します。ZIPの `Shaders/VRM2Skyrim/Licenses` にCommunity Shadersのライセンス文書（`COPYING.txt`、`EXCEPTIONS.md`、`THIRD_PARTY.md`、`LICENSE-Perapechka-MIT.txt`）を同梱し、変更した2つのファイルの先頭に変更の告知を記載しています。HLSLのファイル自体が対応するソースコードです。

## English

Toon shading is enabled by default and can be changed in STEP 01. It carries source MToon shade colours, MatCaps, parametric rim lighting,
world-space outlines and normal maps into opted-in VRM face, body, hair and
clothing materials. Backgrounds, ordinary NPCs and fitted Skyrim equipment keep
their existing rendering. Lighting is adapted for Skyrim.

Authored effect colours, masks, normal strength and lighting mix are retained.
Absent effects stay absent. Source image resolution and repeat, clamp-to-edge
and mirrored-repeat addressing are preserved. Outlines use skinned inverted
hulls owned by the same clothing/head component; their widths use source metres
and the linear green width mask. They follow equipment visibility and FSMP bones
without participating in contact generation. Original geometry, normals, UVs,
weights, binds, partitions and alpha remain unchanged.

Screen-coordinate outlines, source emission textures and UV animation are not
supported. Screen-coordinate widths are rejected explicitly during conversion.
Legacy 8x4, Prototype 4 face and Prototype 5 material markers remain readable.

To use all new effects, re-export the follower with the updated converter and
toon shading enabled in STEP 01, or install a supplied material update
patch for that exact follower. The toon shader ZIP
`VRM2Skyrim-Toon-Shader-0.13.0.zip` is for the Community Shaders installed by
the Nexus release **Bottled Shaders 1.0.22** (DLL version 1.9.0.0). Other
releases such as Bottled Shaders 1.0.4 report the same DLL version but ship
different shaders, so the ZIP does not fit them. Save it with the wizard's **Download the toon shader** button
(in STEP 01 and on the result page), or take the same ZIP from the
`toon-shader` folder of VRM2Skyrim. Disable older shader prototypes and
material patches. Install the ZIP with Vortex / MO2 after Community Shaders,
deploy, back up the actual shader cache while Skyrim is closed, and restart
through SKSE. Keep Screen Space GI enabled. Shader compilation can take time.
Blender previews do not run this adapter.

Beside the download button, the wizard compares the game folder's
`Data/Shaders/Lighting.hlsl` and `Data/Shaders/DeferredCompositeCS.hlsl`. The
original Bottled Shaders 1.0.22 files mean the ZIP is the next step; the ZIP's
own files mean it is installed; anything else gets a warning that the ZIP is
for Bottled Shaders 1.0.22 and may break rendering with this Community Shaders.
When the files are not there (MO2 keeps the shaders in its own mods folder), the
wizard says it could not check and names the release the ZIP is for. Toon
shading stays selectable.

To revert, restore the previous material-and-shader pair, deploy, back up the
cache again and restart. Disable the toon shader ZIP before updating Community
Shaders.

The Prototype 6 shader was built for Bottled Shaders 1.0.4 and does not work
with 1.0.22. After updating to Bottled Shaders 1.0.22, disable the Prototype 6
shader, install this ZIP and back up the shader cache. Follower material
patches remain compatible.

### Licence

VRM2Skyrim itself is MIT-licensed. The toon shader ZIP contains the Community
Shaders files `Lighting.hlsl` and `DeferredCompositeCS.hlsl`, modified by
VRM2Skyrim on 2026-10-28 for VRM toon shading, so the ZIP's contents (including
the bundled `VRM2Skyrim/*.hlsli`) are distributed under GPL-3.0 with the
Community Shaders Modding Exception and GPL-3.0 Linking Exception. The ZIP's
`Shaders/VRM2Skyrim/Licenses` folder holds the Community Shaders licence files
(`COPYING.txt`, `EXCEPTIONS.md`, `THIRD_PARTY.md`,
`LICENSE-Perapechka-MIT.txt`), each modified file starts with a notice of the
change, and the HLSL files are themselves the corresponding source.

## Rebuilding the shader ZIP (maintainers)

The committed `toon-shader/VRM2Skyrim-Toon-Shader-<VERSION>.zip` must be
rebuilt after HLSL changes and on every `settings.VERSION` bump; tests fail
when it is missing or its `adapter.json` differs from `toon.py`. Build it from
the original `Shaders` folder of the Bottled Shaders 1.0.22 mod folder, not an
installed, already-patched one:

```powershell
.\.venv\Scripts\python.exe toon.py --shader-root "<Original Bottled Shaders 1.0.22 MOD>/Shaders"
```

The source Lighting and DeferredComposite hashes must equal `SUPPORTED_LIGHTING`
/ `SUPPORTED_COMPOSITE`; other sources are rejected. The licence files are
taken from `SKSE/Plugins/CommunityShaders/Licenses` in the same mod folder;
`--licenses <folder>` names another folder. The ZIP contains no DLL, embeds
this file as its README, and is not installed into the game. `--diagnostic`
builds a separate, unshipped ZIP in `build/toon-shader` that paints marked VRM
surfaces magenta for activation checks.

## Development verification

`tests/compile_toon.py` compiles 28 original/patched Lighting pairs (including
compile-time Linear Lighting, Effects 11, Night Eye, hair backlighting and fur
shells) and seven DeferredComposite pairs; excluded shaders remain
byte-identical.
`tests/toon_effects_gpu.py` compares atlas addressing, float controls, MatCap
axes, Fresnel, mirrored/rotated UV normals and degenerate UVs against independent
references on hardware D3D11. `tests/toon_effects_quality.py` requires all four
effects to visibly change the complete CS output and tests transparent depth
writes and render phases. The native NIF/DDS fixture retains source culling,
alpha and ZBUFFER_WRITE, renders opaque/cutout before transparent phases, and
checks ordinary materials, darkness, corrupt markers and native GBuffer/SSGI.
Full pipeline validation and animation checks remain separate from final
in-game appearance acceptance.
