# トゥーン描画ガイド (Community Shaders 対応)

VRM Skyrim Converter は、元の VRM アバターに設定された **MToon 材質（影色・明暗の境界・リムライト・MatCap・輪郭線）** を読み取り、Skyrim 内でアニメ調の質感として再現する「トゥーン描画」に対応しています。

他の一般 NPC や背景、フォロワーに着せた Skyrim 既存の鎧・武器の見た目には影響せず、**トゥーン描画を有効にして作成した VRM フォロワー本体の肌・顔・髪・元の衣服だけ**に適用されます。

---

## 1. 必要な環境

トゥーン描画を使うには、Skyrim 側に以下の 3 つが必要です。

1. **SKSE64**（`skse64_loader.exe` からゲームを起動すること）
2. **Community Shaders（Bottled Shaders 1.0.22 / `CommunityShaders.dll` バージョン `1.9.0.0`）**
3. **トゥーン描画用シェーダー ZIP**（`VRM2Skyrim-Toon-Shader-0.13.0.zip`）
   - ウィザードの **STEP 01** または **変換完了画面** にある **「トゥーン描画用シェーダーをダウンロード」** ボタンから保存できます（リポジトリ内の `toon-shader/VRM2Skyrim-Toon-Shader-0.13.0.zip` と同じものです）。
   - 1 回導入すれば、作成した複数の VRM フォロワーで共通して使えます。

> [!IMPORTANT]
> **対応する Community Shaders の配布版について**
> 同梱の `VRM2Skyrim-Toon-Shader-0.13.0.zip` は、Nexus Mods で配布されている **Bottled Shaders 1.0.22**（Mod Organizer 2 等で `Bottled Shaders` として導入される、`CommunityShaders.dll` バージョン `1.9.0.0` のパッケージ）専用です。
> 同じ DLL バージョン `1.9.0.0` であっても、`Bottled Shaders 1.0.4` など他の配布版とはシェーダー本体（`Lighting.hlsl` / `DeferredCompositeCS.hlsl`）の内容が異なるため、そのまま重ねて使うことはできません。

> [!NOTE]
> トゥーン描画を使わない場合は、STEP 01 の「トゥーン描画を使う」のチェックを外してフォロワーを作成してください。その場合は SKSE64 や Community Shaders がなくても通常のフォロワー MOD として動作します。

---

## 2. 導入手順（MO2 / Vortex）

### 手順 1：ウィザードの STEP 01 でトゥーン描画を有効にする

1. ウィザードの **STEP 01（アバターと制作環境）** にある **「トゥーン描画（Community Shaders 用）」** を確認します（初期状態で **「トゥーン描画を使う」** にチェックが入っています）。
2. STEP 01 または完了画面の **「トゥーン描画用シェーダーをダウンロード」** から **`VRM2Skyrim-Toon-Shader-0.13.0.zip`** を保存します。
3. STEP 05 まで進んでフォロワー MOD の ZIP を作成・保存します。

### 手順 2：Mod Organizer 2 (MO2) で導入する場合

1. **Community Shaders 本体（`Bottled Shaders 1.0.22`）** を導入して有効化します。
2. **`VRM2Skyrim-Toon-Shader-0.13.0.zip`** を「アーカイブから MOD をインストール」で追加し、左ペインの並び順で **Community Shaders 本体より下（優先度が高い側）** に置いて有効化します。
   - `Shaders/Lighting.hlsl` と `Shaders/DeferredCompositeCS.hlsl` が `VRM2Skyrim-Toon-Shader` 側で上書きされる状態にします。
3. 作成した **フォロワー MOD の ZIP** をインストールして有効化し、右ペインの「プラグイン」タブで `<フォロワー名>.esp` にチェックが入っていることを確認します。
4. **ゲームを終了した状態で**、Skyrim の `Data/ShaderCache` フォルダ（MO2 の `Overwrite` 内に `ShaderCache` が出力されている場合はそちらも）を別名に退避または削除します。
5. MO2 から **`skse64_loader.exe`** で Skyrim を起動します。

### 手順 3：Vortex で導入する場合

1. **Community Shaders 本体（`Bottled Shaders 1.0.22`）**、**`VRM2Skyrim-Toon-Shader-0.13.0.zip`**、および作成した **フォロワー MOD の ZIP** を Vortex に追加して有効化します。
2. ファイル競合のルール確認が表示されたら、`VRM2Skyrim-Toon-Shader-0.13.0` を **Community Shaders 本体より後（After / 優先）** に設定し、**Deploy Mods** を実行します。
3. 「プラグイン」タブで `<フォロワー名>.esp` が有効になっていることを確認します。
4. **ゲームを終了した状態で**、`Data/ShaderCache` フォルダを別名に退避または削除してから **`skse64_loader.exe`** で起動します。

---

## 3. 元 VRM から引き継がれる MToon 表現

トゥーン描画では、手動で数値を調整する代わりに **元の VRM ファイルに含まれる MToon 材質（`VRMC_materials_mtoon`）の設定値**を自動で読み取って変換します。

- **引き継がれる要素**
  - 基本色テクスチャ・乗算色・アルファ透過（`OPAQUE` / `MASK` / `BLEND`）・両面描画設定（`doubleSided`）
  - 影色（`shadeColorFactor`）と影色テクスチャ（`shadeMultiplyTexture`）
  - 明暗境界の鋭さ（`shadingToonyFactor`）と境界位置（`shadingShiftFactor`）
  - 環境光の均一化設定（`giEqualizationFactor`）と暗所での最低環境光下限
  - ノーマルマップと凹凸の強さ（`normalTexture.scale`）
  - MatCap テクスチャと加算色（`matcapTexture` / `matcapFactor`）
  - リムライトの色・強さ・広がり・光源追従・リムマスクテクスチャ（`parametricRimColorFactor` / `parametricRimFresnelPowerFactor` / `parametricRimLiftFactor` / `rimLightingMixFactor` / `rimMultiplyTexture`）
  - 実寸幅（`worldCoordinates`）の輪郭線（太さ・色・輪郭線幅マスク `outlineWidthMultiplyTexture`）
- **現在の変換で省略される要素**
  - 画面比率（`screenCoordinates`）指定の輪郭線、自己発光テクスチャ（`emissiveTexture`）、UV アニメーションは未対応のため省略されます。
- **設定 JSON での指定キー**
  - 設定 JSON ファイル（`--settings`）で切り替える場合のキーは `"toon_enabled": true`（または `false`）のみです。

> [!TIP]
> **Screen Space GI や既存防具との併用**
> Community Shaders の **Screen Space GI** は有効のまま併用できます。また、フォロワーに Skyrim 既存の鎧や武器を着せた場合、それらの装備品には通常の Skyrim 質感（金属や革の陰影）がそのまま使われます。

---

## 4. 注意点とトラブルシューティング

- **Community Shaders 本体を更新するとき**
  Community Shaders 本体を新しいバージョンへ更新する際は、先に `VRM2Skyrim-Toon-Shader-0.13.0.zip` を無効化してから更新してください。
- **フォロワーが通常のリアルな陰影のまま表示される場合**
  1. `skse64_loader.exe` から起動しているか確認してください。
  2. `Data/Shaders/Lighting.hlsl` と `Data/Shaders/DeferredCompositeCS.hlsl` が `VRM2Skyrim-Toon-Shader-0.13.0.zip` のもので上書きされているか確認してください。
  3. ゲームを一度終了し、`Data/ShaderCache`（および MO2 の `Overwrite/ShaderCache`）を別名に退避してから起動し直してください。古いシェーダーキャッシュが残っていると変更後のシェーダーが読み込まれません。

---

## 5. 技術仕様とライセンス（開発者向けリファレンス）

- **NIF と制御テクスチャの構造 (`toon.py`)**
  - トゥーン対象の `BSLightingShaderProperty` には Glowmap シェーダータイプ（`ShaderType=2`、`SLSF1_Cast_Shadows`、`SLSF2_Glow_Map`、`EmissiveColor=(0,0,0)`、`EmissiveMultiple=0.0`）を設定し、テクスチャスロット 2（シェーダー側の `t6` Glowmap）に制御テクスチャ `textures/<asset_dir>/toon_<hash>.dds` を割り当てます。
  - 制御テクスチャの 1 行目（左端 4 ピクセル）には識別マーカー（通常シェイプは `R=18, G=229, B=164, A=255`、背面押し出しの輪郭線シェイプは `R=19, G=229, B=164, A=255`）と、MToon の影色・境界・リムライト・MatCap・法線強度・輪郭線色を記録します。影テクスチャ・リムマスク・MatCap がある場合は、同じアトラス内の縦 3 段（256×768）に連結して格納します。
  - `Shaders/VRM2Skyrim/ToonCommon.hlsli`・`ToonLighting.hlsli`・`ToonComposite.hlsli` が `t6` のマーカーを検査し、一致したピクセルのみ MToon 計算へ分岐させます（マーカーを持たない一般の Glowmap メッシュは `EmissiveMultiple` がそのまま働くため影響を受けません）。
- **シェーダー ZIP の再ビルド方法**
  手元に展開した `Bottled Shaders 1.0.22` の `Shaders` フォルダを指定して、以下のコマンドで `toon-shader/VRM2Skyrim-Toon-Shader-0.13.0.zip` を再生成・検証できます：
  ```powershell
  .venv\Scripts\python.exe toon.py --shader-root "<Bottled Shaders 1.0.22 の展開先>\Shaders"
  ```
- **ライセンス表記**
  - `VRM2Skyrim` 本体のソースコードは [MIT License](../LICENSE) です。
  - `VRM2Skyrim-Toon-Shader-0.13.0.zip` に含まれる `Shaders/Lighting.hlsl`、`Shaders/DeferredCompositeCS.hlsl`、および `Shaders/VRM2Skyrim/*.hlsli` は Community Shaders（Bottled Shaders 1.0.22）のシェーダーを改変したものであり、**GPL-3.0（Community Shaders Modding Exception および GPL-3.0 Linking Exception 付き）** の下で配布されます。ライセンス全文はシェーダー ZIP 内の `Shaders/VRM2Skyrim/Licenses/` およびリポジトリの [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) に同梱されています。
