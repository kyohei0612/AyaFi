# Architecture

詳細は [ADR-001](decisions/001-initial-architecture.md) を正とする。本ファイルは
「今どこに何がある」のマップ。

## モジュール責務

### `src/aya_afi/` (Python sidecar)

| モジュール | 責務 | 禁止事項 |
|---|---|---|
| `affiliate/moshimo.py` | もしも API 呼び出し、商品 URL → アフィリンク変換 | 文章生成、SNS 投稿 |
| `affiliate/rakuten.py` | 楽天 Web Service API 呼び出し | 文章生成、SNS 投稿 |
| `llm/base.py` | LLM プロバイダ共通 Protocol | 具体実装 |
| `llm/gemini.py` | Gemini API 呼び出し (無料枠前提) | 他 LLM の知識 |
| `llm/ollama.py` | ローカル Ollama 呼び出し | HTTP 固定 (localhost:11434) 前提 |
| `poster/threads.py` | Threads Graph API で投稿 | 文章生成 |
| `poster/bluesky.py` | atproto SDK で投稿 | 文章生成 |
| `poster/note.py` | playwright で note に文章ペーストのみ | 投稿ボタン押下 (禁止) |
| `storage/models.py` | pydantic モデル (Post, Product, SnsAccount) | DB 操作 |
| `storage/db.py` | SQLite + alembic マイグレーション | ビジネスロジック |
| `config/settings.py` | pydantic-settings でグローバル設定 | ハードコード |
| `config/md_loader.py` | `config/*.md` を構造化データにパース | ファイル書き込み |
| `ipc/protocol.py` | Tauri ↔ Python の JSON メッセージ型 (pydantic) | ビジネスロジック |
| `ipc/server.py` | stdin/stdout ループ、ディスパッチ | ビジネスロジック |
| `utils/paths.py` | dev / PyInstaller 凍結環境の両対応パス解決 (config / DB / logs) | ビジネスロジック |
| `utils/logging.py` | stdlib logging + python-json-logger + TimedRotatingFileHandler セットアップ | 具体ログ出力 |
| `cli/` | CLI モード (sidecar 死亡時フォールバック) | UI 固有処理 |
| `__main__.py` | `python -m aya_afi` で sidecar 起動 | ビジネスロジック |

### `src-tauri/` (Rust)

| ファイル | 責務 |
|---|---|
| `src/main.rs` | Tauri エントリ、ウィンドウ起動、sidecar spawn |
| `src/commands.rs` | `invoke` ハンドラ (最薄、sidecar に転送のみ) |
| `src/sidecar.rs` | Python sidecar プロセス管理、再起動 |
| `src/fs_open.rs` | ログフォルダを OS のファイラで開くコマンド (妻向け UX) |
| `tauri.conf.json` | ウィンドウサイズ、ショートカット、バンドル設定 |

### `scripts/` (最薄エントリのみ)

| ファイル | 責務 |
|---|---|
| `sidecar.py` | Tauri からの spawn 対象。`src/aya_afi/ipc/server.py` を呼ぶだけ |
| `cli.py` | CLI フォールバック。`src/aya_afi/cli/` を呼ぶだけ |

### `ui/` (React + TypeScript)

| ディレクトリ | 責務 |
|---|---|
| `src/components/` | プレゼンテーショナルコンポーネント (ロジック持たない) |
| `src/pages/` | 画面 (入力 / エディタ / 投稿履歴) |
| `src/hooks/` | Tauri invoke ラッパー |
| `src/types/` | sidecar と共有する型定義 (pydantic から自動生成予定) |

## データフロー (投稿 1 件)

```
[UI] 商品 URL + プルダウン選択
  ↓ invoke("generate_post", {url, hook, tone, emoji})
[Tauri] sidecar に転送
  ↓ stdin: {"action":"generate_post", ...}
[Python]
  1. affiliate/ で商品情報取得 + アフィリンク生成
  2. config/md_loader で指針を読む
  3. llm/ で文章生成
  4. storage/ に Draft として保存
  ↓ stdout: {"draft_id":"...", "text":"..."}
[Tauri] UI に返す
  ↓ UI に表示
[UI] 妻が編集 → 「投稿」押下
  ↓ invoke("publish", {draft_id, targets:["threads","bluesky"]})
[Python]
  1. storage/ から draft 取得
  2. Threads / Bluesky に投稿 (poster/)
  3. 本文を pyperclip でクリップボードにコピー (note 用の手ペースト支援)
  4. storage/ に結果記録
  ↓ stdout: {"results":[...]}
[UI]
  ├─ 結果トースト: 「Threads / Bluesky 投稿完了。note 用にクリップボードへコピー済」
  └─ 「note で開く」ボタン (投稿ボタン隣に常設) を強調表示

[UI] 妻が「note で開く」押下
  ↓ invoke("open_note_compose")
[Tauri Rust]
  shell.open("https://note.com/notes/new")  ← OS 既定ブラウザで開く
[妻]
  note タブで Ctrl+V → タイトル入力 → note 側の投稿ボタンを押す
```

## 運用パス

妻 PC 上で sidecar が読み書きするパス。全て `utils/paths.py` で解決すること。
ハードコード禁止 (プロチェック rule 4)。

| 用途 | 開発環境 | 凍結環境 (妻 PC) | 種別 |
|---|---|---|---|
| config デフォルト (読取専用) | `./config/` | `sys._MEIPASS/config/` | **exe 同梱** |
| config ユーザー版 (書込可) | `./.user_config/` | `%APPDATA%\aya-afi\config\` | **ユーザー** |
| SQLite | `./aya_afi.sqlite` | `%APPDATA%\aya-afi\aya_afi.sqlite` | ユーザー |
| logs | `./logs/app.log` | `%APPDATA%\aya-afi\logs\app.log` | ユーザー |
| drafts | `./drafts/` | `%APPDATA%\aya-afi\drafts\` | ユーザー |
| secrets | `./secrets/.env` | `%APPDATA%\aya-afi\secrets\.env` | ユーザー |
| alembic スクリプト | `./alembic/` | `sys._MEIPASS/alembic/` | exe 同梱 |

### config 2 段構えの動作

1. 起動時、ユーザー版 config が存在しなければデフォからコピー展開
2. 以降はユーザー版を優先読込、存在しないキーだけデフォから補完
3. UI に「デフォルトに戻す」ボタン: ユーザー版ディレクトリをクリア → 再展開

## IPC 型同期方針

- `src/aya_afi/ipc/protocol.py` で pydantic モデルを Single Source of Truth として定義
- CI で `datamodel-code-generator` (or `pydantic-to-typescript`) により TS 型を自動生成
- 出力先: `ui/src/types/generated/ipc.ts`
- 生成物は commit する (CI で diff チェック、ズレたら落ちる)
- `.pre-commit-config.yaml` + `pnpm dev` の preflight にフックし、Pydantic 編集時に TS 側も自動更新
- 詳細は ADR-003 (予定) で確定

## 下書き自動保存

LLM で文章生成した直後、投稿前に必ず `drafts/<timestamp>-<slug>.md` に保存。
投稿成否・dry-run にかかわらず保存する。

目的:
- SNS API が落ちても生成文を失わない (妻の「せっかく書いたのに!」を防ぐ)
- 過去の文章を参照して書き直しやすくする
- デバッグ時に LLM 出力の履歴を辿れる

保持期間: 90 日 (以降は自動削除、設定で変更可)。

## 今後の TODO

- 各 ADR が確定するたび、該当セクションをこのファイルに追記する
- v0.1 完成時に構成図を画像化して埋め込む
