# AyaFi

SNS アフィリエイト投稿支援アプリ (Windows 専用、ローカル動作)。

内部識別子は `aya-afi` / `aya_afi` のまま (慣習維持)。表示名は **AyaFi**。

## インストール (利用者向け、v0.1 以降)

1. リリースページから `aya-afi-setup-x.x.x.exe` をダウンロード
2. ダブルクリック → SmartScreen 警告が出たら「詳細情報 → 実行」
3. 初回起動時、`%APPDATA%\aya-afi\secrets\.env` にサンプルが展開される。API キーを記入
4. タスクトレイアイコンから起動

## 開発者向けセットアップ

前提: Windows 11 / pnpm / Python 3.12 / Rust (stable)

```powershell
git clone <repo>
cd aya-afi-ver1

# Python sidecar
uv venv
uv pip install -e ".[dev]"

# Frontend + Tauri
pnpm install
pnpm tauri dev
```

## テスト

```powershell
pytest -q                 # Python
pnpm test                 # Frontend
cargo test --manifest-path src-tauri/Cargo.toml
```

## ドキュメント

- [CLAUDE.md](CLAUDE.md) - 全体概要
- [docs/architecture.md](docs/architecture.md) - 構成図
- [docs/runbook.md](docs/runbook.md) - 運用手順
- [docs/decisions/](docs/decisions/) - ADR (意思決定履歴)
