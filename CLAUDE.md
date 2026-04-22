# AyaFi (内部ディレクトリ: aya-afi-ver1)

妻 (aya) が Windows ローカルで使う、半自動 SNS アフィリエイト投稿アプリ。
表示名は **AyaFi**。内部の Python パッケージ / Cargo クレート / APPDATA フォルダは
慣習維持のため `aya_afi` / `aya-afi` のまま。

## 概要

- **投稿先 SNS**: Threads / Bluesky (公式 API 自動) / note (文章ペースト補助のみ、投稿ボタンは人手)
- **アフィ**: もしもアフィリエイト経由で Amazon + 楽天 (実績ゼロで即スタート可)
- **LLM**: Gemini 2.5 Flash 無料枠 → 将来的に Ollama (ローカル、妻 PC の RTX 2070)
- **配布形態**: Tauri で単一 `.exe`、妻 PC に配布

## 技術スタック

| レイヤー | 技術 |
|---|---|
| UI | Tauri (Rust) + React + TypeScript |
| ロジック | Python 3.12 sidecar (PyInstaller で同梱) |
| 通信 | JSON over stdin/stdout (pydantic メッセージ) |
| DB | SQLite + alembic (投稿履歴永続化) |
| 設定 | `config/*.md`, `config/app.yaml`, `.env` |

## ディレクトリ構成

```
aya-afi-ver1/
├── src/                  # Python sidecar = 本体ロジック (プロチェック準拠)
│   └── aya_afi/
├── src-tauri/            # Tauri (Rust): ウィンドウ / IPC / ショートカット
├── ui/                   # React + TS フロントエンド
├── tests/                # pytest
├── scripts/              # CLI エントリのみ (最薄)
├── docs/
│   ├── architecture.md   # 構成図 + モジュール責務
│   ├── runbook.md        # 運用手順
│   ├── style_guide.md    # コンテンツ・台本ルール
│   └── decisions/        # ADR
├── config/
│   ├── app.yaml          # グローバル設定
│   ├── global.md         # SEO / 購買心理の指針
│   ├── sns/              # SNS 別ルール
│   └── prompts/          # プルダウン選択肢
└── secrets/
    └── .env              # API キー (gitignore)
```

## 開発ルール (必読)

`C:\Users\kyohei\Downloads\プロチェックmd.txt` のエンジニアリング憲章 13 ルールを厳守。
加えて本プロジェクト固有のルール 14-21 (投稿前 dry-run / SQLite 履歴 / #PR 自動付与 /
レート制限 / シークレット分離 / UI ガード / Windows 固定 / LLM 抽象化) を適用。

実装前に必ず `docs/decisions/` に ADR を書く。ADR なしで実装着手しない。

## 動かし方 (v0.1 予定)

詳細は `docs/runbook.md` 参照。

```powershell
# 開発
pnpm install
pnpm tauri dev

# リリースビルド
pnpm tauri build
```

## 意思決定履歴

- [ADR-001: 初期アーキテクチャ](docs/decisions/001-initial-architecture.md) — 承認済
- [ADR-002: MVP (v0.1) スコープ確定](docs/decisions/002-mvp-scope.md) — 承認済
- [ADR-003: IPC プロトコル](docs/decisions/003-ipc-protocol.md) — 承認済
- [ADR-004: LLM プロバイダ抽象化](docs/decisions/004-llm-provider-abstraction.md) — 承認済
- [ADR-005: 投稿履歴 + 整合性](docs/decisions/005-post-history-and-integrity.md) — 承認済
- [ADR-006: note 投稿方式 (案 3 追認)](docs/decisions/006-note-paste-assist.md) — 承認済
- [ADR-008: ロギング戦略](docs/decisions/008-logging-strategy.md) — 承認済
- [ADR-009: SNS 別コンテンツ生成エンジン](docs/decisions/009-sns-content-generation-engine.md) — 承認済
- [ADR-010: エラーハンドリング UX](docs/decisions/010-error-handling-ux.md) — 提案中
- [ADR-011: 配布署名戦略](docs/decisions/011-code-signing.md) — 提案中
- [ADR-012: Threads 運用アルゴリズム戦略](docs/decisions/012-threads-algorithm-strategy.md) — 提案中

## 連絡

主開発者: kyohei / 利用者: aya (妻)
