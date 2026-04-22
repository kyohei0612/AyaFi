# Runbook (運用手順)

本ファイルは v0.1 リリース後に本格的に書き起こす。
現時点ではプレースホルダ。

## 初期セットアップ (妻 PC 向け、v0.1 以降)

1. インストーラ実行
2. `secrets/.env.example` → `.env` にコピー
3. 各 API キー・トークンを記入
4. 起動

## よくあるトラブル

### Sidecar が起動しない

(v0.1 実装後に追記)

### Gemini の無料枠上限に達した

- 日次 1500 req が上限。超過時はエラー表示
- 翌日 0:00 (PT) にリセット

### 投稿が失敗した

- ログ `%APPDATA%\aya-afi\logs\` を確認
- 構造化ログの `event` と `error_type` で原因特定

## ログ確認

```powershell
Get-Content "$env:APPDATA\aya-afi\logs\app.log" -Tail 50
```

## バックアップ

投稿履歴 DB: `%APPDATA%\aya-afi\aya_afi.sqlite`
定期バックアップ推奨。
