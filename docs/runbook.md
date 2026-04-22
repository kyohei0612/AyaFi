# Runbook

開発 / 配布 / 運用の手順メモ。

## 開発

```powershell
# 依存セットアップ (初回のみ)
uv venv
uv pip install -e ".[dev,llm,sns]"
pnpm install

# dev 起動
pnpm tauri dev
```

## リリース (aya PC に自動配布)

### 事前準備 (一度だけ)

1. GitHub リポジトリの **Settings → Secrets and variables → Actions** を開く
2. 以下の Secret を登録:
   - `TAURI_SIGNING_PRIVATE_KEY`: `.tauri-keys/ayafi.key` の中身を貼り付け
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: 鍵にパスワードを付けなかった場合は空文字のまま登録

秘密鍵の中身を取り出す:

```powershell
Get-Content .\.tauri-keys\ayafi.key -Raw
```

### リリース手順

```powershell
# バージョン番号を src-tauri/tauri.conf.json と package.json で揃えて更新
# (例: 0.1.0 → 0.1.1)

git add src-tauri/tauri.conf.json package.json
git commit -m "chore: bump to v0.1.1"
git tag v0.1.1
git push origin main --tags
```

`v*` タグが push されると `.github/workflows/release.yml` が:
1. PyInstaller で sidecar.exe をビルド
2. Tauri が NSIS インストーラー (.exe) を生成 + 署名
3. GitHub Release を自動作成 (latest.json + 署名付きインストーラー)

aya PC 上で AyaFi を次回起動すると、updater プラグインが Release を検出して
ダイアログを出し、承諾すれば自動でダウンロード・インストール・再起動します。

## aya PC への初回インストール

1. https://github.com/kyohei0612/AyaFi/releases から最新の
   `AyaFi_*_x64-setup.exe` をダウンロード
2. ダブルクリックしてインストール (ユーザー領域、管理者権限不要)
3. 初回起動前に `secrets/.env` を配置:
   - `%APPDATA%\AyaFi\secrets\.env` (手動作成) に、開発 PC の
     `secrets/.env` をコピー
4. 起動 → メイン UI が開けば OK

## 鍵を失くしたら

`.tauri-keys/ayafi.key` が消えると **新しい鍵で署名し直した v0.x は旧バージョン
から update 不可** になります (公開鍵不一致で弾かれる)。その場合は aya さんに
新インストーラーを手動で渡して入れ直してもらう必要があります。鍵は別マシンに
もバックアップしておくこと。

## ログ

アプリ起動時の動作ログは `%APPDATA%\AyaFi\logs\` に保存されます。
UI のフッター「うまく動かない時はこちら」ボタンでフォルダが開きます。

## よくあるトラブル

### Gemini の無料枠上限に達した

- 1 日 20-1500 req (モデル・プランで変動)。超過時は 429 エラー
- 翌日 0:00 (太平洋時間) にリセット
- `.env` の `LLM_MODEL` を `gemini-2.5-flash-lite` 等に切替で当面回避

### 投稿が失敗した

- ログ `%APPDATA%\AyaFi\logs\` を確認
- 構造化ログの `event` と `error_type` で原因特定
- Threads 画像: catbox.moe 側ダウン時は 0x0.st に自動フォールバック
