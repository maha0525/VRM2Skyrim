# Experimental VRM-only toon shading

[English](#english) | [日本語](#日本語)

## 日本語

これは **MToon風の陰影を試す版**です。元VRMから変換した身体・顔・髪・衣装の材質だけを対象にし、背景や通常のNPCには従来の計算を使います。MToonの影色と明暗の境界を参考にし、陰影を段階化します。夜でも一定の明るさで光る方式ではありません。

最初のアダプターは、2026-10-15に検証した **Community Shaders DLL 1.9.0.0** と、その環境の `Shaders/Lighting.hlsl` に対応します。DLLのバージョンが同じでもシェーダーファイルが異なる版があるため、生成時はSHA256も照合します。未検証のファイルを自動で書き換えません。

### 試作4で変わる見た目

Screen Space GIを有効にしたまま、対象VRMに後から付くAOの陰影を除きます。背景・通常NPCのAOと間接光は残ります。

顔は元VRMの影用テクスチャと影色を使い、一律の暗化を外します。形状や法線は変えません。

肌・髪・元衣装の明暗差を強め、強い光で色が白く潰れるのを抑えます。
VRM材質の環境反射・濡れた鏡面反射も抑えます。暗い場所では暗くなり、霧と透過は残ります。
これはMToon完全互換ではなく、Skyrim向けに照明を調整する試作です。

以前のトゥーン材質も引き続き使えます。**新しい顔の陰影には、フォロワーの再出力か、そのフォロワー用の顔パッチが必要**です。
旧シェーダー試作MODを無効化し、試作4だけを有効にしてDeployしてください。
その後、下記手順のキャッシュ退避とSKSEからの再起動を行います。

### 適用を見分けたい場合

`VRM2Skyrim-Toon-Shader-Prototype-4-Diagnostic.zip` は確認専用です。
他の試作版を無効化し、確認版だけを有効にしてDeploy、キャッシュ退避後に起動します。
**Screen Space GIを有効にしたまま、トゥーン対象のVRM部分が陰影のないピンクになる**のが成功の目印です。
背景や通常NPC、Skyrimの装備は元の表示です。
確認後は確認版を無効化して通常の試作4へ切り替え、同じ手順でDeploy・キャッシュ退避・再起動してください。

### ゲームで試す

まず、Community Shadersを別途導入した環境で、VRM2Skyrimのフォルダから次を実行して専用アダプターを作ります（セットアップ済みのPythonを使用）。`<Skyrim>` は実際のゲームフォルダに置き換えてください。

```powershell
.\.venv\Scripts\python.exe toon.py --shader-root "<Skyrim>/Data/Shaders" --output build/toon-prototype
```

対応するシェーダーソースなら、`build/toon-prototype/VRM2Skyrim-Toon-Shader-Prototype-4.zip` を生成します。既にアダプターを導入している場合は、生成元に元のCommunity Shaders MODの `Shaders` フォルダを指定するか、ゲーム終了中にアダプターを無効化してDeployし、元のCSシェーダーに戻してから実行してください。変更済みのファイルも非対応として拒否します。それでも非対応と表示された場合は、そのCS環境では使えません。MO2の場合も元のCS MODの実際の `Shaders` フォルダを指定します。このコマンドはゲームへ配置しません。

1. Skyrimを終了します。
2. 下記のウィザード設定で生成したフォロワーZIPをVortex / MO2で導入します。既存フォロワーを更新する場合は同じMOD IDのZIPを置き換え、旧版と新版を同時に有効にしません。トゥーン描画の切替だけなら、元VRMとセーブを削除する必要はありません。
3. `VRM2Skyrim-Toon-Shader-Prototype-4.zip` を別MODとして導入します。**Community Shadersより後に読み込み、`Shaders/Lighting.hlsl` と `Shaders/DeferredCompositeCS.hlsl` はこの試作版を優先**します。VortexではDeployします。このZIPにはCS本体のDLLは入りません。
4. コンパイル済みシェーダーを退避します。ゲーム終了中に、Skyrimの **`Data/ShaderCache` フォルダを別名へ変更**してください。例：`ShaderCache-before-toon`。キャッシュは次の起動で作り直されます。MOD本体や `Data/Shaders` は移動しません。
5. SKSEから起動し、シェーダーのコンパイルが終わるまで待ちます。変換したフォロワーの顔・衣服・髪の明暗の境界を確認します。背景、床、通常のNPCは従来の表示のままです。光源に対して向きを変え、屋内外でも確認してください。

MO2でキャッシュをOverwriteへ出している構成では、その実際のキャッシュを退避します。

戻すときは、**シェーダー試作MODを無効化してDeployし、キャッシュを再度退避して再起動**します。試作用の材質自体は発光量0なので、シェーダーが無ければ通常の陰影へ戻ります。必要ならフォロワーZIPも通常版へ戻せます。Community Shadersを更新する場合も、先にこのシェーダー試作MODを無効化してください。

### ウィザードから使う

`main` の0.11.0以降で `Launch.cmd` を開き、STEP 02の「実験的なトゥーン描画」を有効にします。既定はOFFです。生成フォロワーと専用のシェーダー試作MODを両方導入してください。通常のBlenderプレビューはトゥーンシェーダーを動かしません。

### この試作の範囲

- VRM 0 / 1の影色・明暗境界・環境光設定を読みます。明るすぎる影色の最大成分は0.55へ抑え、暗い影色と色相は保ちます。環境光の係数は0.6です。直接光と環境光を合成し、明暗の両側に共通の露出補正を掛けます。
- 顔の影用テクスチャに対応します。顔以外の影テクスチャ、MatCap、リムライト、輪郭線はまだ移植していません。MToonそのものの完全実装ではありません。
- 既存のSkyrim装備を体型に合わせたメッシュは、通常のシェーダーを使います。元VRMの着脱衣装と顔・髪の表示切替用メッシュは対象です。
- FSMPの骨・ウェイト・非表示衝突メッシュと透過順序を保持します。衝突用メッシュにはマーカーを付けません。
- ゲームと同じCSのピクセルシェーダーを、実NIF/DDSとともに画面非表示のD3D11で描画して比較しています。対象外、シェーダーを外した場合、無照明の比較を行います。ゲーム内の描画順や実際の照明との最終確認は、上の導入手順で行います。

### 開発

`python toon.py --shader-root "<Skyrim>/Data/Shaders" --output build/toon-prototype`

このコマンドは互換性を確認して出力先へZIPを作り、ゲームには配置しません。
`tests/compile_toon.py` は元と試作の21組のLightingシェーダーと5組の後段合成シェーダーをコンパイルし、対象外の組のバイトコード一致を検査します。
`tests/toon_gpu_fixture.py` と `tests/toon_gpu.cpp` は実NIF/DDSを読み、元と試作のCSピクセルシェーダーをD3D11で比較します。

開発時はWindows SDKのFXCとMSVCが必要です。コンパイル後、`python tests/toon_gpu_fixture.py --base <通常版の変換出力> --marked <試作版の変換出力> --output build/toon-prototype/gpu --compiled-shaders build/toon-prototype` で実描画と比較まで行います。

2026-10-15の試作検証：16組のコンパイルに成功し、対象外の6組は元と同じバイトコードでした。アイフィ34形状のD3D11比較では、対象外・通常シェーダーへの復帰・無照明の画像差はすべて0でした。全変換は113,125三角形とFSMPを保持し、75フレームの骨格検査に通りました。Pythonの109テスト、Ruff、ブラウザーでの既定OFF・設定保存・再読み込みも通っています。

## English

This prototype applies MToon-like lighting only to opted-in source VRM
materials. It preserves the existing path for unmarked geometry. It reads
VRM 0/1 shade color, toony and shift values, equalizes directional ambient
lighting, and reads the original shade controls. Face shade textures are supported in Prototype 4. Shade textures on other
parts, matcaps, rim lights and outlines are outside this prototype.

Prototype 3 keeps existing follower markers compatible: no follower re-export is
needed. It caps pale shade multipliers at 0.55 (preserving hue and darker shades),
uses 0.6 ambient strength, and bounds illumination with shared exposure for both
bands. Marked surfaces no longer output physical reflections or diffuse GI to
later passes. Prototype 3 also bypasses Screen Space GI ambient occlusion and
indirect-light reception on marked surfaces only; ordinary pixels keep both.
Keep Screen Space GI enabled when checking the diagnostic for residual shading. Darkness, transparency, fog and ordinary materials are preserved.
This is an artistic Skyrim adaptation, not an exact MToon implementation.

Disable other prototypes before enabling Prototype 4, deploy, back up the shader cache
and relaunch through SKSE. The optional
`VRM2Skyrim-Toon-Shader-Prototype-4-Diagnostic.zip` paints recognized VRM surfaces
solid magenta. Use it alone to check activation. Afterwards switch back to the
normal prototype, deploy, back up the cache and restart again.

The first adapter is pinned to the tested Community Shaders 1.9.0.0 installation
and Lighting.hlsl SHA256 `5cb3f71e483d6aba661f9adb10ac8d06db36878f6d6f05c4c8ec383be9fd40e8`.
The builder rejects unverified sources. It never installs into the game.

Use version 0.11.0 or later on `main`. In STEP 02, enable the experimental toon
option (off by default) and generate the follower. Create the separate adapter
from the installed Community Shaders sources with the setup environment:

```powershell
.\.venv\Scripts\python.exe toon.py --shader-root "<Skyrim>/Data/Shaders" --output build/toon-prototype
```

Replace `<Skyrim>` with the game directory. The source must be the original,
unmodified CS shader. If an adapter is already installed, point to the original
CS mod's `Shaders` folder, or close Skyrim, disable the adapter and deploy to
restore the original shader first. For MO2, use the original CS mod's actual
`Shaders` folder. The resulting ZIP is
`build/toon-prototype/VRM2Skyrim-Toon-Shader-Prototype-4.zip`. An unsupported
source is rejected; do not install the adapter with a different CS source.

Install the generated follower ZIP and the separate shader prototype ZIP.
Give the prototype priority over Community Shaders for `Shaders/Lighting.hlsl`
and `Shaders/DeferredCompositeCS.hlsl`.
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

## Licenses / ライセンス

The adapter contains shader code from Community Shaders' MIT-licensed
`package/Shaders` directory and this project's MIT-licensed additions. Both
license texts and copyright notices are included in the generated ZIP.
Community Shaders' DLL and C++ sources are not bundled.

アダプターにはCommunity ShadersのMIT対象ディレクトリのシェーダーと、本プロジェクトのMITの追加処理を含みます。両方のライセンス全文・著作権表示を生成ZIPへ同梱します。CS本体のDLLとC++ソースは同梱しません。

## Prototype 2 verification / 試作2の検査

`tests/toon_quality.py` compares the actual full CS pixel shaders using exported
NIF/DDS geometry and a uniform curved surface. It checks visible two-band
contrast, 4x/16x illumination, dim light, linear and legacy lighting, invalid
markers, diagnostic isolation and all deferred diffuse/specular/reflectance
outputs. The ordinary reflection fixture must produce reflections before the
marked path is allowed to claim their suppression. Ordinary deferred outputs
remain pixel-identical. These are offscreen D3D11 tests, not game screenshots.

Lighting-band reference: [VRMC_materials_mtoon 1.0](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_materials_mtoon-1.0/README.md#lighting).


## Prototype 3 verification / 試作3の検査

The activation gate no longer assumes SKINNED is defined on pixel shader
permutations. The full Lighting -> native-format GBuffer -> DeferredComposite
GPU check supplies positive AO/IL inputs. Quon and Aifi pixels receive AO in
the previous diagnostic, and no AO/IL in the new diagnostic; ordinary pixels
keep their original AO/IL results in both legacy and linear lighting modes.
The diagnostic and normal ZIPs use the same marker and deferred ownership path.

Both source files are pinned by SHA256. Neither ZIP changes the game's global
Screen Space GI settings. Existing follower exports remain compatible.


## Prototype 4 face update / 顔の更新

Install the Prototype 4 shader ZIP after disabling older shader prototypes.
The authored-face path requires a follower exported with this version, or a
matching head patch installed with priority over that follower. Existing 8x4
materials retain Prototype 3 appearance. Keep Screen Space GI enabled, deploy,
rename Data/ShaderCache with the game closed, then relaunch through SKSE.
To remove a head patch, disable it to restore the follower's original meshes.

Faces keep their original shade RGB and receive equalized ambient light through
the lit colour, without the prototype's 0.55 shade cap. Geometry, normals, skin
weights and bind transforms stay unchanged. The default legacy path remains
available for other parts. One-mip BC7 textures keep source resolution; repeat
padding prevents the metadata strip from bleeding into UV seams. UV0 with
identity texture transforms and repeat addressing is currently supported.

顔パッチは元のフォロワーMODより優先してください。対応する顔パッチを使う場合、再出力は不要です。
顔の形状・法線・ウェイトは変わりません。戻す場合は顔パッチを無効化します。
