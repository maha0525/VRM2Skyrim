# 出力フォーマット・内部レコード仕様 (Output Format & Record Specification)

このドキュメントでは、**VRM Skyrim Converter** が生成するプラグイン（`.esp`）、メッシュ（`.nif`）、テクスチャ（`.dds`）、および設定メタデータの内部仕様をまとめています。

---

## 1. ローカル FormID の割り当て規則

フォロワーのプラグイン（`.esp`）内では、各レコードに固定または予約されたローカル FormID（内部ファイルインデックス `1`）を割り当てます。セーブデータとの互換性を保つため、一度割り当てた ID を別のレコード種別に転用することはありません。`TES4` ヘッダ（`HEDR`）の次オブジェクト ID は常に `0x900` 以上に設定されます。

| ローカル ID | レコード種別 | 役割 / 実装箇所 |
| :--- | :--- | :--- |
| `0x800` | `NPC_` | フォロワー本体の Actor レコード (`build_npc.NPC_ID`) |
| `0x801` | `ARMO` | 固定外観、または全身の Skin アーマー (`build_npc.ARMOR_ID`, `gear_head_runtime` FullSkin) |
| `0x802` | `ARMA` | 固定外観、または素体（Body）の Skin アドオン (`build_npc.ADDON_ID`) |
| `0x803` | `OTFT` | デフォルト衣装 (`build_npc.OUTFIT_ID`) |
| `0x804` | `RACE` | フォロワー専用種族 (`build_npc.RACE_ID`) |
| `0x805` | `RELA` | プレイヤーとの関係レコード (`build_npc.RELATIONSHIP_ID`) |
| `0x806` | `ACHR` | ワールド（ホワイトラン・キナレス聖堂）に配置される参照 (`build_npc.REFERENCE_ID`) |
| `0x807`–`0x80A` | `ARMA` | 下着・固定顔/髪・手・足の Skin アドオン (`build_npc.appearance_records`) |
| `0x80B` | `ARMO` | 旧仕様の頭部カバー用予約枠（現在はマスク 0 の非活性レコードとして保持, `head_visibility.HEAD_COVER_ID`） |
| `0x80C` / `0x80D` | `HDPT` / `FLST` | 空の HeadPart と頭部用種族リスト (`head_visibility`) |
| `0x810`–`0x82F` | `ARMA` / `ARMO` | 着脱可能な元の衣服（最大 16 品：ARMA `0x810 + 2n`, ARMO `0x811 + 2n`, `wardrobe.MAX_GARMENTS`） |
| `0x830`–`0x83F` | （予約領域） | `wardrobe.py` 用予約枠 |
| `0x840`–`0x846` | `FLST` | 衣装ランタイム管理リスト (`equipment_runtime.LIST_IDS`) |
| `0x850` / `0x851` | `ARMA` | 分離された顔・髪の Skin アドオン (`build_npc.appearance_records`) |
| `0x852`–`0x854` | `ARMO` | 顔非表示・髪非表示・両方非表示の切り替え用 Skin (`gear_head_runtime.IDS`) |
| `0x855` / `0x856` | `FLST` | 顔を隠す装備リスト / 髪を隠す装備リスト (`gear_head_runtime.IDS`) |
| `0x860`–`0x862` | `ARMA` | 頭部表示切り替え用バリアントアドオン (`gear_head_runtime.head_variants`) |
| `0x870` | `FLST` | 着席高さ補正の対象となる椅子・ベンチのリスト (`seating.SEATS_ID`) |
| `0x880` | `CSTY` | フォロワー専用の戦闘スタイル (`combat_style.CUSTOM_STYLE_ID`) |
| `0x880`–`0x8BF` | `ARMA` | 旧仕様の体型合わせアドオン領域（過去のプロファイル読み込み時のみ認識, `armor_patch.py`） |
| `0x8D0` | `WEAP` | オリジナル武器レコード (`weapon.WEAPON_ID`) |
| `0x8D1` | `STAT` | オリジナル武器の 1 人称モデルレコード (`weapon.FIRST_PERSON_ID`) |
| `0x1000` 以降 | `ARMA` | 体型合わせ済みの公式装備アドオン（元アドオンごとに 1 件, `armor_fitting.py`） |

---

## 2. プラグイン・NPC レコード仕様

バイナリフィールドの構造は [xEdit の TES5 定義 (`wbDefinitionsTES5.pas`)](https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.5/Core/wbDefinitionsTES5.pas) に準拠しています。

- **マスターファイル (`TES4` / `MAST`)**
  - 基本マスターは `Skyrim.esm`（および必要に応じて `Update.esm`）です。
  - 体型合わせした防具の足音（`SNDD`）や、DLC のシャウト（`SHOU`）を使用する場合のみ、該当する公式 DLC / Creation がマスター一覧へ重複なく追加され、内部の FormID インデックスが実際の `MAST` 順に再マッピングされます（`follower_plugin.py`, `shouts.py`）。
- **NPC 基本設定 (`ACBS` / `AIDT` / `DNAM` / `PRKR` / `SPLO`)**
  - `ACBS`: フラグ（`Unique=0x20`, `Female=0x1`, `Essential=0x2`, `Protected=0x800`, `AutoCalc=0x10`, `PCLevelMult=0x80`）、マジカ・スタミナ・体力の初期オフセット、レベル範囲を保持します。
  - `AIDT`: 攻撃性、自信、道徳観（犯罪への態度）、仲間への援助フラグ（`Assistance=2`: 友人と仲間を助ける）を設定します。
  - `DNAM`: 18 種のスキル値とオフセット、および基礎ステータスを保持します。手動でスキルを指定した場合は `AutoCalc=false` になります。
  - `PRKR`: 選択された Perk の FormID とランクを記録します。
  - `SPLO`: 選択された呪文（`SPEL`）とシャウト（`SHOU`）の両方を格納し、`SPCT` に合計件数を書き込みます。
- **フォロワー雇用システムと配置 (`FACT` / `RELA` / `ACHR`)**
  - `CurrentFollowerFaction`（ランク `-1`）、`PotentialFollowerFaction`（ランク `0`）、およびプレイヤーとの `Ally` 関係（`RELA`）を設定することで、バニラ標準の勧誘・待機・解雇・持ち物交換ダイアログをそのまま使用します。
  - 配置参照（`ACHR` `0x806`）はホワイトランのキナレス聖堂（`WhiterunTempleofKynareth`）の永続参照として配置されます。

---

## 3. 骨格・メッシュ・マテリアル変換仕様

- **カスタムスケルトンとリターゲティング**
  - アニメーション制御される Skyrim 標準ボーンのローカル変換を維持したまま、VRM のプロポーションを合わせる非アニメーション親ヘルパーノードを挿入します。
  - バニラ骨格に存在しない杖の納刀ノード `WeaponStaff` を `NPC Spine2` の子として追加し、背中に杖を背負えるようにしています（`custom_skeleton.HELPER_NODES`）。
- **FaceGen ヘッドの無効化**
  - 専用種族（`RACE` `0x804`）の `DATA` フラグから `FaceGen Head` ビット（`0x2`）を落とし、空の `HDPT`（`0x80C`）とメッシュなしの `FaceGeom` を配置することで、装備を着脱してもバニラの人間頭部が VRM の顔の上に重なって描画される現象を防いでいます。
- **マテリアルと両面描画フラグ (`doubleSided`)**
  - glTF / VRM の ` OPAQUE`、`MASK`、`BLEND` に応じて `NiAlphaProperty` を設定し、テクスチャを BC7 / BC1 DDS に変換します。
  - 元のマテリアルの `doubleSided` 設定（初期値 `false`）をそのまま `BSLightingShaderProperty` の `SLSF2_Double_Sided` に反映します。片面マテリアルに強制的に両面描画フラグを立てないことで、まつ毛や目の裏面ポリゴンが白目を覆ってしまう現象を防いでいます。

---

## 4. 衣装の分離と Biped スロット仕様

STEP 01 で「衣服・防具の分離（`armor_support=True`）」を有効にした場合、メッシュの役割に応じて以下のスロットとレコードが生成されます。

- **素体・下着・頭部（Skin レコード）**
  - 素体（Body：Slot 32）、常時表示する下着（Underwear：Slot 52）、顔と髪（Face/Hair：Slot 60 等）を個別の Skin `ARMA` として出力します。
  - 素体メッシュは胴体（`32/34/38`）・手（`33`）・足（`37`）のパーティションに分割され、小手やブーツを着けた部位だけ素体が隠れるように構成されます。
- **着脱可能な衣服アイテム（Garment レコード）**
  - `wardrobe_policy=native_slots` では、胴体衣装は Slot `32`（パーティション `32/34/38`）、手は `33`、足は `37`、頭装備は `30/31`、サークレットは `42`、マントやバッグ等の追加装飾は拡張スロット（`44–49`, `53–59`）を使用します。
  - 上下一体型の全身衣装（`item_kind=full`）を Slot 32 に割り当てた場合は、Slot `32/33/37` を占有します。
  - 初期装備の衣服は NPC の所持品（`CNTO`）に入り、初回ロード時（`OnInit`）に装着されます。以降の着せ替えは Skyrim 標準の Biped スロット排他制御によって自然に切り替わります。

---

## 5. 既存防具の体型合わせと登録方式

- **体型合わせメッシュの生成 (`armor_fitting.py`)**
  - 選択されたバニラ・DLC・Creation 防具の元 NIF を BSA から展開し、ボーンセグメントの位置合わせと表面補正によって VRM の体型へ変形します。
  - 防具内のバニラ素体メッシュは除去し、露出部分には元の VRM の素体メッシュ（頂点・UV・法線・ウェイトを維持）を組み込みます。
- **フォロワー別の独立登録（SkyPatcher 併用時 / 0.12.0 以降）**
  - フォロワーごとに独立した `ARMA`（`0x1000` 以降）と、`<フォロワー名>.esp.ini`（SkyPatcher ルール）および頭部表示切り替えリスト（`FLST` `0x855` / `0x856`）を同梱します。
  - 元の `ARMO` レコードを直接上書きしないため、他の防具 MOD や他の VRM フォロワーと競合せず、統合防具パッチの作り直しも不要です。
- **Outfit Studio 編集の上書き保存 (`outfit_edits.py`)**
  - 完了画面から書き出した `OutfitStudio-EditKit.zip` のメッシュを編集して再インポートすると、アバターの SHA256 と装備アドオン識別子をキーとして頂点座標と法線の差分が保存され、同じアバターを再変換した際にも手直し結果が自動で引き継がれます。

---

## 6. オリジナル武器（GLB）の変換仕様

`weapon_mode="original"` を選んだ場合、アップロードされた `.glb` から専用武器レコード（`WEAP` `0x8D0`）と 1 人称モデル（`STAT` `0x8D1`）を生成し、初期所持品に登録します。

- **ベース武器の継承**
  - 8 種類の武器カテゴリ（片手剣 `SteelSword`、ダガー `SteelDagger`、片手斧 `SteelWarAxe`、メイス `SteelMace`、両手剣 `SteelGreatsword`、両手斧 `SteelBattleaxe`、戦槌 `SteelWarhammer`、杖 `StaffFlames` 等）から選ばれた `Skyrim.esm`（および `Update.esm`）の武器レコードを複製し、攻撃力・重量・モーション種別・サウンドを引き継ぎます。
- **座標系・グリップ位置・コリジョン生成 (`weapon.py`, `weapon_nif.py`)**
  - GLB の最長バウンディングボックス軸を `+Y`（刃先・先端方向）に揃え、`length`（全長）と `grip`（下端からの把持位置の割合）、`flip`（前後反転）、`roll`（軸回転）を適用します。
  - 最大 48 頂点の凸包（`bhkConvexVerticesShape`）から重心・慣性テンソル・`bhkRigidBody` を計算し、`meshes/<asset_dir>/weapon.nif` として出力します。
- **PBR テクスチャの変換**
  - ベースカラー（`weapon.dds`）、法線＋グロスマップ（`_n.dds`、アルファに `1 - roughness`）、および金属度マスク（`_m.dds`、金属領域が 1% 以上ある場合）を生成し、金属マテリアルには環境マップ `textures\cubemaps\ShinyDull_e.dds` を設定します。
