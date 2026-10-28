# フォロワーのシャウト — ウィザードでシャウトを覚えさせる

ステータス: 設計中 (2026-10-28 起草)。実装は未着手。

## 出てくる名前

- シャウト: Skyrim の竜の言葉の技。ゲームのデータでは `SHOU` レコードで、三つの言葉 (`WOOP` レコード) と、言葉の数ごとの効果の魔法 (`SPEL` レコード) と、使ったあとに次に使えるまでの待ち時間を持つ。
- `SPLO`: NPC レコードの中の「使える魔法の一覧」。魔法 (`SPEL`) もシャウト (`SHOU`) も、ここに入れる。`SPCT` はその数。
- ESP・FormID・マスター: [original-weapon.md](original-weapon.md) の「出てくる名前」と同じ意味。
- Editor ID: レコードに付く英字の識別名 (`DLC2CycloneShout` など)。FormID とは別に、人が読むための名前として付いている。
- プラグイン名: 公式のデータファイルの名前 (`Skyrim.esm`・`Dragonborn.esm` など)。
- `OfficialCatalog`: インストールされた公式のデータファイル (`Skyrim.esm`・`Update.esm`・DLC・Creation) を読み、レコードを `ファイル名:番号` (例: `Dragonborn.esm:0200C0`) の形のキーで引けるようにする、このツールの既存の仕組み (`official_catalog.py`)。今は防具に関係するレコード (`ARMO`・`ARMA`・`TXST`) だけを読んでいる。
- 体型合わせ: 公式の防具をフォロワーの体型に合わせて変換する、このツールの既存の機能 ([armor-fitting.md](armor-fitting.md))。合わせた防具の足音の記録が DLC にあると、フォロワーの ESP のマスターにその DLC が足される (`skypatcher.footstep_bindings`)。
- 戦闘スタイルの「シャウトの優先度」: 戦闘スタイル (`CSTY`) の `Equipment Score Mult - Shout`。ウィザードの戦闘スタイルの編集に既にある項目で、詳細の欄に入っている ([custom-combat-style.md](custom-combat-style.md))。

## 何をするか

ウィザードで、フォロワーにシャウトを覚えさせられるようにする。選んだシャウトをフォロワーの `SPLO` に入れ、フォロワーが戦闘で使えるようにする。DLC (Dragonborn) のシャウトの「サイクロン」も選べるようにする。

動機は、SAIVerse のペルソナ (エア) が「風魔法を使いたい」と言っていて、Skyrim には風の魔法が無いので、風を使うシャウト (サイクロンや揺るぎ無き力) で叶えたいこと (まはーの言葉、2026-10-28)。

## まはーが決めたこと (2026-10-28)

- ウィザードでフォロワーにシャウトを覚えさせる方法を設計する。DLC のサイクロンも含める。

この節に無い項目は、すべて書き手 (メティス) の提案である。

## ゲームのデータで確かめたこと (2026-10-28)

- `Skyrim.esm` には、`SPLO` にシャウトを持つ NPC が 290 人いる (入っているシャウトは合わせて 485 件)。プレイヤーが覚えるのと同じシャウトを持つ NPC もいる。ウルフリック (`MQ304Ulfric`) は `UnrelentingForceShout` (揺るぎ無き力) と `DisarmShout` を、ウルフガー (`Wulfgar`) はグレイビアード専用のシャウトと一緒に、プレイヤーと同じ `WhirlwindSprintShout` (旋風の疾走) を持っている。だから、プレイヤー用のシャウトをフォロワーの `SPLO` に入れる形で、フォロワーに使わせられると私は考えている。
- NPC 専用のシャウトもある。`UnrelentingForceShoutDraugr` (ドラウグル用の揺るぎ無き力) では、三つ目の言葉の効果が二つ目と同じ `VoiceUnrelentingForce2` になっている。`DLC2MiraakCycloneShout` (ミラーク用のサイクロン) では、言葉に仮の言葉 (`MQFakeWord`) が使われ、待ち時間が 10 秒になっている。ドラウグル用のように三つ目の言葉の効果を弱めた NPC 専用のシャウトがわざわざ作られているので、NPC は三つ目の言葉まで使うのだと私は推測している (ゲームでは未確認)。
- 戦闘スタイルの「シャウトの優先度」は、よく使う `csHumanMagic`・`csHumanMeleeLvl1`・`csHumanBoss2H`・`csHumanMissile` がどれも 1.0 だった。0 ではないので、これらの戦闘スタイルのフォロワーはシャウトを使うと考えられる (ゲームでは未確認)。
- サイクロン (`DLC2CycloneShout`) は `Dragonborn.esm` のレコードで、`OfficialCatalog` のキーは `Dragonborn.esm:0200C0`。言葉は `DLC2CycloneWord1`〜`3`、待ち時間は 30・45・60 秒。
- `Update.esm` の中にシャウトのレコードは無く、DLC の中で本体のシャウトが上書きされている例も無かった。

## 選べるシャウト

プレイヤーが覚えられるシャウトを候補にする。NPC 用・竜用・クエスト用の版 (`Dragon…`・`…Draugr`・`Greybeard…`・`DLC2Miraak…`・`MQ…` など) は候補にしない。

プレイヤーが覚えられるシャウトを、データから機械的に見分ける規則は見つからなかった。「三つの言葉が全部違い、仮の言葉や竜の言葉を含まず、説明文がある」で絞っても、狼男の遠吠え (`HowlWerewolfCallOfTheWild`)・試験用の `MQ105PhantomFormShout`・竜用の `DLC1DragonDrainVitalityShout02` などが混ざった。だから候補は、コードに書いた一覧 (プラグイン名と Editor ID の組) にする。

一覧に入れるのは次の 27 個 (書き手の提案)。

- `Skyrim.esm` (20): `animalAllegianceShout`・`AuraWhisperShout`・`BecomeEtherealShout`・`CallDragonShout`・`CallofValorShout`・`ClearSkiesShout`・`DisarmShout`・`Dismay`・`DragonrendShout`・`ElementalFuryShout`・`FireBreathShout`・`FrostBreathShout`・`IceFormShout`・`KynesPeaceShout`・`MarkedforDeathShout`・`SlowTimeShout`・`StormCallShout`・`ThrowVoiceShout`・`UnrelentingForceShout`・`WhirlwindSprintShout`
- `Dawnguard.esm` (3): `DLC1DrainVitalityShout`・`DLC1SoulTearShout`・`DLC1SummonDragonShout` (デュルネヴィール召喚。言葉が `DLC1DragonSummon1Dur`〜`3Viir` で説明文がある。似た名前の `DLC1VQ05DurnehviirShout` はクエスト用で、候補にしない)
- `Dragonborn.esm` (4): `DLC2BattleFuryShout`・`DLC2BendWillShout`・`DLC2CycloneShout`・`DLC2DragonAspectShout`

一覧の扱いは次のとおり。

- プラグインがインストールされていないシャウトは、候補に出さない。
- プラグインはインストールされているのに一覧のレコードが見つからないときは、データが壊れているか想定と違うので、候補の作成をエラーで止め、どのシャウトが見つからないかを画面に出す。
- 今の `OfficialCatalog` ではシャウトのレコード (`SHOU`) を読み込んでいないため、読み込み対象に `SHOU` を加える。また、今の `require` では全プラグインをまとめた Editor ID の辞書からレコードを検索しているため、「プラグイン名と Editor ID の組」で検索する処理を足す。

候補の中には、フォロワーが戦闘で使うのか分からないものがある (旋風の疾走・晴天の空・声投げなど)。竜召喚 (`CallDragonShout`) とデュルネヴィール召喚は、効果のスクリプトがプレイヤーが使う前提で作られていて、フォロワーが使っても働かない可能性もある (未確認)。画面ではシャウトの説明文と一緒に「戦闘で使うかどうかはゲームで確かめていない」と書く。

## ウィザード

- STEP 04「得意技を加える」に、Perk と魔法の欄と並べてシャウトの欄を足す。表示はシャウトの名前と説明文 (日本語と英語、[wizard-localization.md](wizard-localization.md))。
- DLC のシャウトには「Dragonborn が必要」のように、必要な DLC を表示する。
- シャウトを一つ以上選んだときは、戦闘スタイルの「シャウトの優先度」の値を一緒に表示する。値は、専用の戦闘スタイルを使っているとき (`combat_style_mode` が `custom`) はその編集後の値、そうでなければ選んだ公式の戦闘スタイルの値にする。値が 0 なら「この戦闘スタイルではシャウトを使わない」と注意を出す。
- 役割のプリセットにはシャウトを含めない。プリセットを当てても、選んだシャウトは変えない。(今のプリセットを当てると公式の戦闘スタイルの選択と魔法が置き換わるが、プリセットにシャウトの値は無いため、シャウトはそのまま残る。)

## 設定

設定 JSON (`settings.py` の `FollowerSettings`) に `shouts` を足す。値は `OfficialCatalog` のキー (`プラグイン名:6 桁の 16 進の番号` の形。サイクロンなら `Dragonborn.esm:0200C0`) の一覧にする。Editor ID ではなくこのキーにするのは、DLC のレコードを同じ形で指すためで、体型合わせの装備の保存と同じ形である ([all-official-equipment.md](all-official-equipment.md))。初期値は空で、今までの設定ファイルも空として読み込む。

設定に入っているシャウトのプラグインがインストールされていない環境で設定を読み込んだときは、黙って外さずにエラーにし、どのシャウトにどの DLC が要るかを画面に出す。検査は `GameCatalog.validate_settings` (今は `Skyrim.esm` だけを見ている) に、`OfficialCatalog` でシャウトを確かめる処理として足す。

## レコード (ESP)

### SPLO と SPCT

- 選んだシャウトを、フォロワーの NPC の `SPLO` に足す。並びは、魔法を先に、シャウトを後にする。`SPCT` は魔法とシャウトの合計にする。今のコードは魔法が空だと `SPCT` を書かないが、シャウトだけを選んだときも `SPCT` を書く。
- シャウトのレコード自体はコピーしない。公式のレコードを指すだけにする。公式のレコードは上書きしない。

### DLC のマスター

- DLC のシャウトを選んだときは、そのプラグインと、そのプラグインが必要とするマスターも順にフォロワーの ESP のマスターに足す (体型合わせの足音と同じ足し方。たとえば `Dragonborn.esm` を足すと、そのマスターの `Update.esm` も足される)。
- これは「フォロワーの ESP のマスターは `Skyrim.esm` だけにする」という古い方針 ([all-official-equipment.md](all-official-equipment.md) の「Keep the follower plugin's existing Skyrim-only master layout」) の例外になる。この方針は 0.12.0 で体型合わせの足音のために既に例外が作られている ([per-follower-armor-registration.md](per-follower-armor-registration.md))。オリジナル武器ではマスターを増やさない側を選んだ ([original-weapon.md](original-weapon.md)) が、それは「元にする公式の武器の候補を絞る」ことでマスターを増やさずに済んだからである。サイクロンはそのレコード自体が `Dragonborn.esm` にあるので、マスターを足さずに使う方法は無い。実装のときに、[all-official-equipment.md](all-official-equipment.md) と [FORMAT.md](../FORMAT.md) の該当する文に、この例外を書き足す。
- マスターの計算は、今は体型合わせを使うとき (`settings.fitting_enabled`) だけ行われている。シャウトは体型合わせなしでも使うので、マスターの計算をその条件の外に出し、足音の分とシャウトの分を合わせて、重複なく、`OfficialCatalog` のプラグインの順に並べる。
- 足音の参照 (`footstep_bindings` が返す番号) は、今は足音のマスターだけの並びで計算されている。シャウトで別の DLC が加わると並びが変わり、番号がずれる (例: 足音で `Update.esm`・`Dragonborn.esm` を足しているところに、シャウトで `Dawnguard.esm` が加わると、`Dragonborn.esm` の番号が 3 から 4 に変わる)。だから足音の参照も、合わせた並びで計算し直す。

### FormID の番号の変換

- `OfficialCatalog` の FormID の上位の番号は、カタログの中だけの番号 (`OfficialCatalog.plugins` の中の位置) である。フォロワーの ESP を組み立てる途中では、`Skyrim.esm` を 0、フォロワー自身を 1、足したマスターを 2 から順の番号で書く決まりになっている (`follower_plugin.write_follower`)。だからシャウトの FormID は、`2 + 合わせたマスターの並びの中の位置` を上位の番号にして `SPLO` に書く (足音の `footstep_bindings` が `extras.index(owner) + 2` でしているのと同じ変換)。`Skyrim.esm` のシャウトは 0 のまま書く。
- そのうえで、書き出すときに本当のマスターの順へ付け替える処理 (`follower_plugin.remap`) で `SPLO` も付け替えられるように、`follower_plugin.py` の `REFS` の `NPC_` に `SPLO` を足す。`Skyrim.esm` の番号 0 は付け替えの対象外なので、今までの魔法には影響しない。

### 最終検査

今の最終検査 (`plugin_validation.validate_private_records`) の参照の検査では、「自分のファイルのレコードを指しているのに、そのレコードが無い」参照だけをエラーにする。シャウトは自分のファイルのレコードを指さないので、そこに `SPLO` を足しても何も確かめられない。だから、シャウトのための検査を別に足す。

- 書き出した ESP をもう一度読み込み、NPC の `SPLO` の各シャウトの FormID の上位の番号が、ESP のマスターの数の範囲に収まっていること。
- その番号が指すマスターのファイルで、指されたレコードが `SHOU` であり、設定の `shouts` のキーと一致すること。
- `SPCT` が `SPLO` の数と一致すること。
- 書き出した ESP のマスターの一覧が、足音とシャウトから計算した一覧と一致すること。

## 配布

DLC のシャウトを持つフォロワーの ZIP は、その DLC が無い人の環境では読み込めない。ZIP に同梱する README に、必要な DLC を書く。今の README には、条件によって「No additional prerequisite MOD is required.」と書く文がある (`converter.py`) ので、DLC が必要なときにこの文と食い違わないように、必要な DLC の一覧を書く形に直す。

## 文書の更新

実装のときに、[FORMAT.md](../FORMAT.md) の付け替え対象の一覧 (「the serializer maps the real MAST order, including VMAD, race, outfit, …」) に `SPLO` を足し、上の「DLC のマスター」の例外を書き足す。

## 最初は対象外にするもの

シャウトの性能や待ち時間の変更、自作のシャウト (風の魔法を新しく作ること)、NPC 用の版 (弱めた版・ミラークの版) を選べるようにすること、Creation (cc で始まるプラグイン) のシャウト。

## ゲームの中で確かめること

- フォロワーが戦闘で、選んだシャウトを実際に使うか。とくに、サイクロン・揺るぎ無き力・旋風の疾走。
- フォロワーが三つ目の言葉まで使うか (上の推測の確認)。
- 竜召喚とデュルネヴィール召喚が、フォロワーが使っても働くか。
- DLC のシャウトを持つフォロワーの ESP が、DLC をマスターにして正しく読み込まれるか。

## 検証

- 上の「最終検査」の四つを、書き出した ESP をもう一度読み込んで確かめる。体型合わせで DLC のマスターが足される設定との組み合わせ (足音の参照がずれないこと) も確かめる。
- 候補の一覧の全部が、インストールされたデータに実在することを確かめる。
- 設定 JSON の書き出しと読み込みで、シャウトが保たれること、プリセットで変わらないこと、DLC が無い環境ではエラーになることを確かめる。
- ブラウザでの操作 (選ぶ・注意の表示・日本語と英語) を確かめる。
- ゲームでの確認は、まはーが行う。それまではゲームでの動作を確認済みとして扱わない。
