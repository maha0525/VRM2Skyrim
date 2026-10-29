# 開発・テスト手順 (Development & Testing)

このドキュメントでは、**VRM Skyrim Converter** の開発者向けに、テスト・静的解析・ブラウザ検証の実行手順と内部仕様ドキュメントの案内をまとめています。

利用者向けのセットアップや使い方については [README.ja.md](../README.ja.md)（英語は [README.md](../README.md)）を参照してください。

---

## 1. 単体テストの実行 (Python unittest)

仮想環境（`.venv`）の Python を使って、`tests/` 配下の単体テストを実行します。

```powershell
.venv\Scripts\python.exe -m unittest
```

特定のテストファイルだけを実行する場合：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_localization
.venv\Scripts\python.exe -m unittest tests.test_toon
.venv\Scripts\python.exe -m unittest tests.test_shouts
.venv\Scripts\python.exe -m unittest tests.test_original_weapon
```

---

## 2. リンター・コード整形チェック (Ruff)

外部依存（`dependencies/`）、ビルド出力（`build/`）、参照データ（`reference/`）を除外して Ruff を実行します。

```powershell
python -m ruff check --exclude dependencies,build,reference .
```

---

## 3. ブラウザ UI テスト (Playwright)

`tests/browser-*.cjs` には、Playwright を使ったウィザード UI の自動テストが含まれています。

### モック API で完結する UI テスト（Skyrim・VRM 実データ不要）

以下のテストは、フィクスチャやモックルートを使ってブラウザ上の表示・日英切り替え・フォーム操作を検証します。

```powershell
node tests\browser-localization.cjs
node tests\browser-shouts.cjs
node tests\browser-original-weapon.cjs
node tests\browser-physics-settings.cjs
node tests\browser-roles.cjs
node tests\browser-saved-results.cjs
node tests\browser-feedback.cjs
```

### ローカルの Skyrim / VRM 実データを使う結合テスト

実際の VRM ファイルや Skyrim のインストール環境を指定して変換フローを検証するスクリプトです。

```powershell
# 起動と環境検出の確認
node tests\browser-startup.cjs

# VRM を指定した衣装分離・防具合わせ・E2E 検証
$env:VRM2SKYRIM_TEST_VRM = "path\to\test.vrm"
node tests\browser-wardrobe.cjs
node tests\browser-fitting.cjs
node tests\browser-native-wardrobe.cjs
node tests\browser-original-headwear.cjs
node tests\browser-skypatcher.cjs
node tests\browser-e2e.cjs
```

---

## 4. 内部仕様と検証記録

- **[docs/FORMAT.md](FORMAT.md)** — 生成される NIF メッシュ、ESP プラグインレコード、DDS テクスチャ、アセット配置の内部仕様
- **[VERIFICATION.md](../VERIFICATION.md)** — 各機能の実装・検証チェックリストと記録
- **[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)** — 外部ライブラリおよびシェーダーのライセンス表記
