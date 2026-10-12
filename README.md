# VRM2Skyrim

**あなたのVRMアバターを、スカイリムの旅の仲間に。**

人型のVRM 0 / 1から、Skyrim Special Edition用フォロワーMODを作るローカルツールです。体型の比率を保つ専用種族・専用骨格を生成し、元の顔・髪・衣装でゲームへ連れていけます。5段階のウィザードで設定し、Vortex / Mod Organizer 2へ導入できるZIPを出力します。

初期配置は**ホワイトランのキナレス聖堂内**。標準フォロワーの派閥・プレイヤーとの友好関係・勧誘用ボイス・永続参照を設定し、会話から仲間にできる構成を作ります。

現在のバージョンは **0.6.0**。固定外観、元衣装の分離装備、既存装備の体型合わせを選べます。0.3のソフィー版フォロワーはSkyrim内でユーザー確認OK。衣服の着脱と新しい装備の体型合わせは、生成／オフライン検証とゲーム内確認を分けて記録します。[検証範囲](VERIFICATION.md)

## 起動する

必要なもの:

- Windows、Python **3.11 / 3.12**。
- Skyrim Special Edition本体（`Skyrim.esm`と本体BSA）。
- **Blender 4.5 LTS**。検証には4.5.12を使用。
- 変換する人型VRM。

1. このリポジトリをclone、またはCode → Download ZIPで取得して展開します。
2. 初回のみ **`Setup.cmd`** を実行します。専用の`.venv`へPython依存を入れ、固定バージョンのPyNifly/texconvを`dependencies/`へ取得します。
3. **`Launch.cmd`** を実行すると、ブラウザでウィザードが開きます。
4. VRMを選び、SkyrimのフォルダとBlenderの実行ファイルを確認します。見つかった環境は自動入力されます。
5. 設定して「フォロワーMODを作る」。完了画面からZIPとプレビューを取得します。

このPC内で処理します。モデルを外部サービスへ送信しません。入力VRM、ゲームのData、セーブを変更しません。ウィザードを閉じるときは、起動したターミナルでCtrl+C。制作中のBlenderのユーザー設定も変更しません。

Blender自体は[公式サイト](https://www.blender.org/download/lts/)から別途導入してください。Creation Kit、SKSE、RaceMenu、XPMSSEは今回の生成MODには追加の前提として要求しません。

## ウィザードで決められること

| 段階 | 設定 |
| --- | --- |
| VRMと環境 | VRMファイル、Skyrim/Blenderの場所、保存済み設定の読み込み |
| 衣服の分離 | 対応なし／あり、メッシュごとの身体・下着・常時表示・衣服の分類、原VRMの分類プレビュー |
| 元衣装の装備 | 一品へ結合／個別に分離、装備名・占有枠・衣服／軽装／重装・防御力・重量・価値・初期装備 |
| 名前と声 | NPC名、MOD名、固有MOD ID、作者、性別、標準フォロワー会話を持つ17種類のボイス |
| 戦闘と能力 | 戦士/両手武器/弓/破壊魔法/召喚魔法のプリセット、クラス、戦闘スタイル、開始武器と矢 |
| 成長と性格 | 固定/プレイヤー追従レベル、倍率・上下限、能力の自動成長/手動指定、体力・マジカ・スタミナ、18スキル、不死/保護/通常、勇敢さ・攻撃性・犯罪への対応 |
| 詳細 | 全体の一様なサイズ倍率、対応ボイスでの結婚候補、聖堂内の配置オフセット |
| 得意技 | Perkとランク、魔法。ゲームの名前/ID/説明から検索 |
| 確認と出力 | 設定JSONの保存、プレビュー生成、MOD ZIPの保存 |

Perk・魔法などの候補は、指定したゲームの`Skyrim.esm`から読みます。DLC・追加MODのPerk/魔法・独自収録ボイスはこの版の候補に含みません。体力・マジカ・スタミナは成長前の基礎値です。種族の基礎値との差をオフセットとして書き込み、レベル追従または自動計算が有効なら、ゲーム側でクラス/レベルに応じた成長分が加わります。個別スキルの指定には手動計算を選びます。

MOD IDからESP名・Editor ID・メッシュ/テクスチャの専用パスを生成します。複数のモデルを同時導入するときは、**異なるMOD ID**を使ってください。NPC名・表示用のMOD名は日本語でも設定できます。

## 身体・下着・衣服を分ける

0.6.0では、衣服を通常のNPC持ち物として追加し、初期装備欄は空にします。NPC専用スクリプトが最初の一回だけ設定された服を着せます。服を取った後に補充したり、AFTの装備セットを書き換えたりしません。

各衣服の「鎧との切替」で、胴の鎧／手袋／靴を優先するグループ、または防具と併用する設定を選びます。変換済みの対応防具を着せると、そのグループの元衣装を自動で外します。服が再装備されても対応防具を優先します。元衣装へ戻すときは対応防具を先に外してください。アイテムは持ち物に残ります。未変換の防具・頭装備はこの切替と表示の対象外です。

「部位・用途」は衣服／防具のキーワード判定、「占有する装備枠」は他の衣服との競合を設定します。SkyUIの種類名・アイコンは主に装備枠で決まり、部位・用途だけでは変更できません。UI MODがマント／バッグとして扱う46／47には用途を表示し、普通の服の分割は53から順に割り当てます。保存済みの枠はそのまま読み込みます。Skyrimには独立した標準のズボン枠がないため、下半身の服も重ね着枠を使います。

0.5.1の内部装備による頭の非表示は、AFTが初期装備を解除すると人間の顔が再出現するため廃止しました。専用種族のFaceGenによる頭の生成を無効にし、NPCと種族には空の頭部モデルを指定します。VRMの顔・髪は素肌の枠60に残り、頭を隠すアイテムの装備状態に依存しません。

旧版と同じESPの新ZIPへ置換・デプロイ後、Skyrimを終了して再起動します。古い3D表示が残る場合だけ、コンソールで対象NPCを選択して`disable`→同じ選択のまま`enable`で再表示します。NPCやセーブは削除しません。既存セーブの持ち物は新規NPCとは異なるため、AFTが保管した服を再生成・複製する移行は行いません。

最初の画面で「対応あり」を選ぶと、VRMのメッシュ一覧に分類候補を表示します。候補は名前と材質からの推定なので、**身体・下着・顔や髪などの常時表示・着脱する衣服を自分で確認**してください。身体と服が一体になっているメッシュを、この版では切断・復元しません。

衣服を一品にまとめるか、個別装備へ分けられます。グループを追加し、各メッシュの装備グループを選ぶことで、複数メッシュを一着にもできます。装備の詳細を開いて品名・枠・能力・初期装備を調整します。「服を外す」や「一品だけ外す」を選び、分類プレビューで身体・下着が残ることを確かめてから変換します。これは原VRMの確認であり、出力NIFの画像は変換後に生成します。

身体・下着・常時表示・各衣服は別NIFへ出力し、同じ専用骨格で動きます。下着は無装備時にも残ります。衣服は44–49／53–59の重ね着枠を使い、身体32・下着52・常時表示60をこのフォロワー用に予約します。同じ枠の品を初期装備で併用する設定は拒否します。全ての品をNPCの持ち物へ追加し、初期装備設定は最初の一回の着用に使います。持ち物・地面での表示はゲーム本体の汎用衣服モデル、着用時は変換した元VRMの形状です。

衣服の分類は入力VRMのSHA256に結び付けます。同じ設定を別VRMへ読み込んだ場合は、最初の画面の「分類候補へ戻す」で新しいモデルを分類し直してください。全ての有効メッシュを一回だけ分類し、取りこぼしや二重登録を拒否します。

生成READMEに、NPCをコンソールで選んで`unequipitem`／`equipitem`を実行する確認手順と衣服のIDが入ります。通常の持ち物会話、AFTの装備管理、解散・セーブ／再読込時の扱いはゲーム内確認が残ります。独自のフォロワー装備UIを追加する機能ではありません。

## Skyrimへ導入する

1. 生成ZIPをVortex / MO2でインストール・有効化。VortexではDeployも実行します。
2. プラグイン一覧で生成された`<MOD ID>.esp`を有効にします。
3. 起動中のSkyrimを終了してから起動し直し、テスト用セーブで**ホワイトランのキナレス聖堂**へ行きます。
4. 話しかけて標準の勧誘会話を選びます。加入、追従、待機、解散、再勧誘を確認してください。

標準フォロワー枠を使います。別の仲間が枠を使っている場合は、先に解散させてください。すでに聖堂へ配置されるので、通常は`player.placeatme`不要です。テスト用に聖堂へ移動するコンソールは `coc WhiterunTempleofKynareth`。

生成READMEには配置参照の検索コマンドと、そのロード順に応じたFormIDを使う手順も入ります。0.1/0.2のSophie試作を使っていた場合、新しいSophieFollowerとは別プラグインなので、旧試作を無効にしたテスト用セーブで確認してください。

## 変換の範囲

- VRM 0 / 1の人型骨格、任意のノード/メッシュ名、必要に応じた大きな形状の分割。
- 元の体型を保つ単位変換と関節回転。標準体型への部位ごとの伸縮はしません。
- 専用種族、専用骨格、固定外観または元衣装の分離装備、標準フォロワー設定と初期配置。
- 位置と方向を照合した副骨格の対応付け。身体と別に作られた服や髪も、同じ出力骨格へ統合。
- OPAQUE / MASK / BLEND材質とDDSのアルファ。表情モーフの初期値は固定外観へ焼き込みます。
- 出力NIF/DDSの読み戻し、元VRMとの同一姿勢の頂点比較、標準歩行/片手剣アニメーションの検査と画像。

対応ありでは、分類した元衣装を着脱できます。独立した身体のあるモデルでは「既存装備をこの身体に合わせる」を選び、本体ゲームの胴・手・足装備を64品まで指定できます。鎧側を変形し、元の肌の頂点・面を保ち、鎧の露出部分へ元の肌を含めます。最初の候補はバンデッド鉄の鎧と鉄のブーツです。ヘルメット・盾・DLC・他MODの装備はこの入力形式の対象外です。

フォロワーZIPに加え、結果画面から**防具互換パッチZIP**も導入します。フォロワーESPの後で`VRM2SkyrimArmorPatch.esp`を有効にし、Vortexではデプロイしてからゲームを再起動してください。変換した本体ゲームの装備を渡すと、設定した切替グループの元衣装を外します。併用に設定した衣服は残ります。確認用のFormIDとコマンドは生成READMEへ入ります。

体型合わせを使うフォロワーが複数いる場合、結果画面で対象を選び、一つの防具パッチへまとめます。インストール済み、またはこのウィザードで変換済みのフォロワーが候補になります。有効な互換パッチは一つにし、対象を追加・削除したら作り直します。元の装備の数値・表示名・元種族のAddonを保持しますが、同じ装備を上書きする他MODとはロード順や追加パッチの調整が必要な場合があります。

口パク・まばたき、髪/衣装の物理は未対応です。MToonの陰影と輪郭線も再現しません。指ボーンがないモデルの指は手へ固定します。転倒・死亡時のラグドール寸法/拘束は標準由来で、アバターへの調整・検証が残ります。

聖堂への配置のため、聖堂のCELLレコードは本体の内容を保ったコピーとして含まれます。同じCELLの照明などを変更するMODと併用する場合は、通常のロード順/互換パッチで調整してください。

原VRM、作業用の基準メッシュ、依存ツールは生成ZIPへ入れません。専用に変換した骨格・外観・装備と、それらが使うテクスチャは入ります。モデルを使う/生成MODを配布する際は、そのモデルの作者の利用条件に従ってください。

## CLIと再変換

```powershell
python converter.py --doctor
python converter.py avatar.vrm --settings my-follower.json
python converter.py avatar.vrm --settings my-follower.json --game 'E:\SteamLibrary\steamapps\common\Skyrim Special Edition' --blender 'C:\path\blender.exe' --output build/my-new-build
python wizard.py --no-browser --port 8768
```

`.venv`で準備した場合は`.venv\Scripts\python.exe`を使います。VRMを`Convert-VRM.cmd`へドラッグしても変換できます。出力は`build/`以下。過去の変換結果は上書きしません。明示した`--output`には空のフォルダを指定してください。

生成ZIPの`vrm2skyrim/<MOD ID小文字>/settings.json`をウィザードへ読み込めば、同じ設定で再変換できます。説明書も同じフォルダの`README.txt`です。VRMを差し替えて別モデルへ使う場合は名前とMOD IDを変更します。0.3/0.4のルートにあった`VRM2Skyrim-settings.json`も引き続き読み込めます。0.4.1では説明書・設定を含む全ファイルをMODごとのパスに分け、別MOD ID同士のファイル競合を解消しました。

## 開発・検証

```powershell
python -m unittest test_converter tests.test_follower tests.test_wardrobe tests.test_package tests.test_armor
python -m ruff check --exclude dependencies,build,reference .
```

フォロワー統合テストにはローカルのSkyrim.esmが必要です。ゲームがない環境ではそのテストだけをskipします。

ブラウザE2Eは専用のヘッドレスブラウザを使い、ユーザーのブラウザプロファイルを操作しません。

```powershell
npm install
npx playwright install chromium
# 別ターミナルで python wizard.py --no-browser を起動
$env:VRM2SKYRIM_TEST_VRM='C:\path\test-avatar.vrm'
npm run test:ui
# 身体・下着・複数の服が分かれたテスト用VRMでは:
npm run test:wardrobe
# 同じ操作に装備選択と防具パッチ作成を含める:
$env:VRM2SKYRIM_TEST_FIT='true'
npm run test:fitting
```

既存のChromeを専用ヘッドレスプロセスとして使う場合は`VRM2SKYRIM_TEST_BROWSER=chrome`。サーバーURLは`VRM2SKYRIM_TEST_URL`で指定できます。

ファイル構造と実装の根拠は[FORMAT.md](docs/FORMAT.md)、設計は[follower-wizard.md](docs/intent/follower-wizard.md)。PyNifly V29.1.0とDirectXTex may2026を外部依存として使用し、取得時に固定SHA256を確認します。それぞれのライセンスはGPL-3.0 / MITです。原VRMとゲーム資産をこのリポジトリへ含めません。

## English quick start

VRM2Skyrim creates fixed-appearance Skyrim SE follower MODs from humanoid VRM 0/1 avatars. The generated follower is placed inside Whiterun's Temple of Kynareth and configured for the vanilla follower system.

On Windows, install Python 3.11/3.12 and Blender 4.5 LTS, then run `Setup.cmd` and `Launch.cmd`. Select the VRM, configure the follower through the local wizard, and install its ZIP through Vortex/MO2. Names, voice type, combat class/style, leveling, stats, skills, perks, spells and initial equipment are configurable. Optional wardrobe mode classifies body, permanent underwear, face/hair and removable original garments. Garments can be grouped or split into separate items with configurable slots and stats. The interface is currently Japanese.

The converter keeps original proportions and private asset paths per MOD ID. With an independent body, select original-game body/hand/foot equipment for fitting. Install both the follower ZIP and its separate armor-patch ZIP; enable the patch after the follower ESP. Remove original VRM wardrobe layers before wearing game equipment. The result page can combine several fitted followers into one patch. Facial animation and physics fitting remain unimplemented. New wardrobe/equipment behavior still requires in-game verification; the earlier Sophie follower was user-confirmed. See [VERIFICATION.md](VERIFICATION.md), [wardrobe design](docs/intent/armor-support.md) and [equipment fitting](docs/intent/armor-fitting.md).
