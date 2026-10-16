# Experimental VRM-only toon shading

[English](#english) | [日本語](#日本語)

## 日本語

試作6は、元VRMのMToon材質に設定された影色・MatCap・リムライト・輪郭線・ノーマルマップを、顔・身体・髪・衣服に反映します。背景、通常NPC、体型合わせしたSkyrim装備は従来の描画を使います。Skyrim向けの照明調整を含む試作で、MToon完全互換ではありません。

### 対応する表現

- 元の影テクスチャ・影色・明暗の境界・環境光設定を使います。強い光での白飛びと、Screen Space GIから後付けされるAO・間接光を対象VRMだけ抑えます。
- MatCap、リムライトの色・強さ・マスク・照明への追従、ノーマルマップの強さを材質ごとに引き継ぎます。設定されていない効果は加えません。
- 輪郭線は実寸幅（worldCoordinates）と幅マスクに対応します。衣服や髪と一緒に着脱・表示切替・揺れへ追従します。画面比率で幅を指定するscreenCoordinatesは未対応で、変換時に通知します。
- 画像の解像度とRepeat / Clamp to Edge / Mirrored Repeatを保ちます。元の形状・法線・UV・スキンは保持し、輪郭線だけ専用の形状を加えます。衝突計算には加えません。
- 元の発光テクスチャとUVアニメーションは未対応です。

### 導入

**試作6の効果には、更新した本体で再出力したフォロワーと、シェーダー試作6の両方が必要です。** 配布された材質更新パッチがある場合は、該当するフォロワーを再出力する代わりに使えます。旧8x4マーカー、顔専用の試作4、全身対応の試作5の材質も、新しいシェーダーで使えます。

1. Skyrimを終了します。
2. 更新した本体のSTEP 02で「実験的なトゥーン描画」を有効にし、フォロワーを再出力してVortex / MO2へ導入します。同じMOD IDの旧版を置き換えます。材質更新パッチを使う場合は元フォロワーより優先します。
3. 以前のシェーダー試作MODと材質更新パッチを無効化し、`VRM2Skyrim-Toon-Shader-Prototype-6.zip` を導入します。Community Shadersより優先させ、VortexではDeployします。
4. ゲーム終了中に実際の `Data/ShaderCache` を別名へ退避します（例：`ShaderCache-before-toon6`）。MO2でOverwriteへ出している場合は、そのキャッシュを退避します。`Data/Shaders` は移動しません。
5. SKSEから起動し、コンパイル終了後に確認します。Screen Space GIは有効のまま使えます。初回はコンパイルに時間がかかります。

通常のBlenderプレビューはこのシェーダーを使いません。

戻す場合は、材質パッチとシェーダーを両方とも以前の組み合わせへ戻し、Deploy・キャッシュ退避・SKSE再起動を行います。Community Shaders本体を更新する場合は、先にこの試作を無効化します。

### シェーダーZIPの生成

検証対象は **Community Shaders DLL 1.9.0.0** と対応するシェーダーソースです。同じDLL版でもソースが異なる場合があるため、SHA256で照合し、未検証の版を拒否します。

```powershell
.\.venv\Scripts\python.exe toon.py --shader-root "<元のCommunity Shaders MOD>/Shaders" --output build/toon-prototype
```

`build/toon-prototype/VRM2Skyrim-Toon-Shader-Prototype-6.zip` を生成します。導入済みの改変されたシェーダーではなく、元のCS MODを指定します。ZIPはDLLを含まず、このコマンドでゲームへは配置しません。

`--diagnostic` を付けると確認専用ZIPを生成します。通常版の代わりに入れると、対象VRMが陰影のないピンクになります。普段の使用には通常版を使ってください。

## English

Prototype 6 carries source MToon shade colours, MatCaps, parametric rim lighting,
world-space outlines and normal maps into opted-in VRM face, body, hair and
clothing materials. Backgrounds, ordinary NPCs and fitted Skyrim equipment keep
their existing rendering. This is an artistic Skyrim adaptation, not full MToon
compatibility.

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
the experimental toon option enabled, or install a supplied material update
patch for that exact follower. Disable older shader prototypes and material
patches. Install `VRM2Skyrim-Toon-Shader-Prototype-6.zip` after Community Shaders,
deploy, back up the actual shader cache while Skyrim is closed, and restart
through SKSE. Keep Screen Space GI enabled. Shader compilation can take time.
Blender previews do not run this adapter.

To revert, restore the previous material-and-shader pair, deploy, back up the
cache again and restart. Disable the adapter before updating Community Shaders.

Build the adapter from the original Community Shaders MOD's `Shaders` folder:

```powershell
.\.venv\Scripts\python.exe toon.py --shader-root "<Original Community Shaders MOD>/Shaders" --output build/toon-prototype
```

It produces `build/toon-prototype/VRM2Skyrim-Toon-Shader-Prototype-6.zip` without
installing it. The tested adapter is pinned to DLL 1.9.0.0 and exact Lighting and
DeferredComposite source hashes. Unsupported or already-modified sources are
rejected. The optional `--diagnostic` package paints marked VRM surfaces magenta;
use the normal package for regular play.

## Development verification

`tests/compile_toon.py` compiles 21 original/patched Lighting pairs and five
DeferredComposite pairs; excluded shaders remain byte-identical.
`tests/toon_effects_gpu.py` compares atlas addressing, float controls, MatCap
axes, Fresnel, mirrored/rotated UV normals and degenerate UVs against independent
references on hardware D3D11. `tests/toon_effects_quality.py` requires all four
effects to visibly change the complete CS output and tests transparent depth
writes and render phases. The native NIF/DDS fixture retains source culling,
alpha and ZBUFFER_WRITE, renders opaque/cutout before transparent phases, and
checks ordinary materials, darkness, corrupt markers and native GBuffer/SSGI.
Full pipeline validation and animation checks remain separate from final
in-game appearance acceptance.
