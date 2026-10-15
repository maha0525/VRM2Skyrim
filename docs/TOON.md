# Experimental VRM-only toon shading

[English](#english) | [日本語](#日本語)

## 日本語

これは **MToon風の陰影を試す版**です。元VRMから変換した身体・顔・髪・衣装の材質だけを対象にし、背景や通常のNPCには従来の計算を使います。MToonの影色と明暗の境界を参考にし、陰影を段階化します。夜でも一定の明るさで光る方式ではありません。

最初のアダプターは、2026-10-15に検証した **Community Shaders DLL 1.9.0.0** と、その環境の `Shaders/Lighting.hlsl` に対応します。DLLのバージョンが同じでもシェーダーファイルが異なる版があるため、生成時はSHA256も照合します。未検証のファイルを自動で書き換えません。

### ゲームで試す

1. Skyrimを終了します。
2. 確認用アイフィのフォロワーZIPをVortex / MO2で導入します。通常版のアイフィを、同じ `Ai_Fi_Follower.esp` の試作版へ置き換えてください。ESPを二つ同時に有効にしません。元VRMとセーブを削除する必要はありません。
3. `VRM2Skyrim-Toon-Shader-Prototype-1.zip` を別MODとして導入します。**Community Shadersより後に読み込み、`Shaders/Lighting.hlsl` はこの試作版を優先**します。VortexではDeployします。このZIPにはCS本体のDLLは入りません。
4. コンパイル済みシェーダーを退避します。ゲーム終了中に、Skyrimの **`Data/ShaderCache` フォルダを別名へ変更**してください。例：`ShaderCache-before-toon`。キャッシュは次の起動で作り直されます。MOD本体や `Data/Shaders` は移動しません。
5. SKSEから起動し、シェーダーのコンパイルが終わるまで待ちます。アイフィの顔・袖・髪の明暗の境界を確認します。背景、床、通常のNPCは従来の表示のままです。光源に対して向きを変え、屋内外でも確認してください。

このPCのキャッシュ場所は `E:\SteamLibrary\steamapps\common\Skyrim Special Edition\Data\ShaderCache` です。MO2でキャッシュをOverwriteへ出している構成では、その実際のキャッシュを退避します。

戻すときは、**シェーダー試作MODを無効化してDeployし、キャッシュを再度退避して再起動**します。試作用の材質自体は発光量0なので、シェーダーが無ければ通常の陰影へ戻ります。必要ならフォロワーZIPも通常版へ戻せます。Community Shadersを更新する場合も、先にこのシェーダー試作MODを無効化してください。

### ウィザードから使う

`codex/vrm-toon-shading` ブランチで `Launch.cmd` を開き直し、STEP 02の「実験的なトゥーン描画」を有効にします。既定はOFFです。生成フォロワーと別配布のシェーダー試作MODを両方導入してください。通常のBlenderプレビューはトゥーンシェーダーを動かしません。

### この試作の範囲

- 影色の倍率、明暗の境界、環境光の方向による濃淡の緩和を実装しています。VRM 0 / 1の設定を読みます。影色の追加係数は0.85です。
- 元VRMの影テクスチャ、MatCap、リムライト、輪郭線はまだ移植していません。MToonそのものの完全実装ではありません。
- 既存のSkyrim装備を体型に合わせたメッシュは、通常のシェーダーを使います。元VRMの着脱衣装と顔・髪の表示切替用メッシュは対象です。
- FSMPの骨・ウェイト・非表示衝突メッシュと透過順序を保持します。衝突用メッシュにはマーカーを付けません。
- ゲームと同じCSのピクセルシェーダーを、実NIF/DDSとともに画面非表示のD3D11で描画して比較しています。対象外、シェーダーを外した場合、無照明の比較を行います。ゲーム内の描画順や実際の照明との最終確認は、上の導入手順で行います。

### 開発

`python toon.py --shader-root "<Skyrim>/Data/Shaders" --output build/toon-prototype`

このコマンドは互換性を確認して出力先へZIPを作り、ゲームには配置しません。
`tests/compile_toon.py` は元と試作の16組のシェーダーをコンパイルし、対象外の組のバイトコード一致を検査します。
`tests/toon_gpu_fixture.py` と `tests/toon_gpu.cpp` は実NIF/DDSを読み、元と試作のCSピクセルシェーダーをD3D11で比較します。

開発時はWindows SDKのFXCとMSVCが必要です。コンパイル後、`python tests/toon_gpu_fixture.py --base <通常版の変換出力> --marked <試作版の変換出力> --output build/toon-prototype/gpu --compiled-shaders build/toon-prototype` で実描画と比較まで行います。

2026-10-15の試作検証：16組のコンパイルに成功し、対象外の6組は元と同じバイトコードでした。アイフィ34形状のD3D11比較では、対象外・通常シェーダーへの復帰・無照明の画像差はすべて0でした。全変換は113,125三角形とFSMPを保持し、75フレームの骨格検査に通りました。Pythonの109テスト、Ruff、ブラウザーでの既定OFF・設定保存・再読み込みも通っています。

## English

This prototype applies MToon-like lighting only to opted-in source VRM
materials. It preserves the existing path for unmarked geometry. It reads
VRM 0/1 shade color, toony and shift values, equalizes directional ambient
lighting, and uses a 0.85 additional shade multiplier. Shade textures, matcaps,
rim lights and outlines are outside this initial prototype.

The first adapter is pinned to the tested Community Shaders 1.9.0.0 installation
and Lighting.hlsl SHA256 `5cb3f71e483d6aba661f9adb10ac8d06db36878f6d6f05c4c8ec383be9fd40e8`.
The builder rejects unverified sources. It never installs into the game.

Install the generated follower ZIP and the separate shader prototype ZIP.
Give the prototype priority over Community Shaders for `Shaders/Lighting.hlsl`.
With Skyrim closed, rename `Data/ShaderCache` to a backup name so the new shaders
are compiled. Deploy and launch through SKSE. Compare the VRM's lighting while
turning near lights; ordinary NPCs and scenery should retain their normal look.

To remove, disable the shader prototype, deploy, rename the cache again, and
restart. The marked NIFs use zero emission and retain normal fallback shading.
Disable this prototype before updating Community Shaders. Existing fitted
Skyrim equipment remains conventionally shaded. Original VRM garments and
face/hair variants are included. FSMP and transparency are retained.

The wizard option is experimental and off by default. Its usual Blender
previews do not execute the runtime toon shader. Offscreen comparisons use
the actual CS pixel shaders with native NIF/DDS inputs in Direct3D 11; they
are not screenshots from a running Skyrim session.
