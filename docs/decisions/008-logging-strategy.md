# ADR-008: ロギング戦略

- **日付**: 2026-04-22
- **ステータス**: 承認済 (2026-04-22)
- **決定者**: kyohei
- **関連**: [ADR-001](001-initial-architecture.md), [ADR-002 Stage 0](002-mvp-scope.md)

---

## Context (問題)

Stage 0 着手前にロギング方針を確定する必要がある。理由:
- Stage 0 で `utils/logging.py` を実装し、以後の全コードがそれを使う
- 後から差し替えるとコード全体で書き換えが発生
- 妻 PC (非エンジニア) でのトラブル時、**ログが妻の手元に残っていないと原因究明不可能**
- プロチェック rule 6「print 禁止、logging モジュールのみ、構造化ログ (JSON)」
- プロジェクト追加ルール 18「シークレットをログに出さない、マスクする」

## Decision (結論)

### Python sidecar 側

- **stdlib `logging`** + `python-json-logger` + `TimedRotatingFileHandler` を採用
- 出力先: `%APPDATA%\aya-afi\logs\app.log` (開発時は `./logs/app.log`)
- **日次ローテ**、過去 30 日分保持
- JSON formatter でフィールド: `timestamp`, `level`, `logger`, `event`, `message`, `context`
- コンソール出力は TTY 判定時のみ (開発時)、凍結環境 (妻 PC) では stdout が Tauri に流れるためファイルのみ
- **シークレットマスクフィルタ**: `.env` の値を正規表現で検知 → `***REDACTED***` に置換
- ログレベル: `config/app.yaml` の `log_level` で制御 (デフォ INFO)

### Rust / Tauri 側

- `tracing` + `tracing-subscriber` + `tracing-appender`
- 出力先: `%APPDATA%\aya-afi\logs\tauri.log`
- Python 側と同じフォルダ、日次ローテ、30 日保持
- JSON フォーマット

### UI 機能

- 「ログフォルダを開く」ボタン (設定画面に配置)
  - Tauri `shell.open(%APPDATA%\aya-afi\logs\)` で OS ファイラを起動
  - 妻がサポート要請時にフォルダごと圧縮してくれる導線

### ログイベント規約

全イベントに最低限以下を含める:
```python
logger.info(
    "post_published",
    extra={
        "event": "post_published",
        "sns": "threads",
        "draft_id": draft.id,
        "success": True,
    },
)
```

重要処理 (副作用あり) は **必ず before / after** の 2 行を出す (プロチェック rule 6)。

### シークレットマスク

`utils/logging.py` に `SecretRedactionFilter` を実装し、
`.env` から読み込んだ全値を辞書にキャッシュ → レコードの全フィールドで部分一致を
`***REDACTED***` に置換。API キー / トークン / パスワードの漏洩を構造的に防止。

---

## Alternatives 検討

### 案 A (採用): stdlib logging + python-json-logger
- ✅ プロチェック rule 6 完全準拠
- ✅ 軽量、依存追加 1 つ
- ✅ TimedRotatingFileHandler が標準装備
- ⚠ loguru ほど API はエレガントではない

### 案 B: loguru
- ✅ API が直感的、構造化ログの実装が楽
- ❌ **プロチェック rule 6「logging モジュールのみ」に抵触** → 却下

### 案 C: structlog
- ✅ 構造化ログに特化、パイプライン設計可能
- ⚠ プロチェック 6 の文言を厳密に取ると抵触、議論余地あり
- ❌ 学習コスト + 依存追加 → 案 A 比のメリット薄い

### 案 D: stdlib のみ、自前 JSON formatter
- ✅ 依存最小
- ❌ 車輪の再発明、python-json-logger で得られる機能を自作する必要なし

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| ログファイル肥大化 | ディスク圧迫 | 日次ローテ + 30 日保持で上限 (概算 30 日で数百 MB 未満) |
| シークレット漏洩 | API キー流出 | `SecretRedactionFilter` で全値を辞書マスク。pytest で「キーが出ない」テスト必須 |
| 凍結環境で書込権限なし | ログ出ずに原因不明 | `%APPDATA%` は書き込み可前提。初回起動時にディレクトリ作成を確認 |
| ログレベルを下げ忘れる | DEBUG のまま出荷 | 設定デフォ INFO、DEBUG にするには UI で明示操作 |
| ローテ中のファイルロック競合 | ログ 1 行消失 | TimedRotatingFileHandler は内部で処理済、多重起動のみ注意 (ADR-001 二重起動防止で別途対処) |
| JSON formatter 例外で本処理停止 | 機能停止 | Formatter に try/except、失敗時は plaintext にフォールバック |

---

## ロールバック手順

1. **JSON が重い / 読みづらい**: Formatter を plaintext に差し替え (1 行変更)
2. **python-json-logger がメンテ切れ**: 同等機能の別ライブラリ (`structlog`, 自前) に差し替え
3. **最悪**: stdlib のみで plaintext logging に戻す (機能劣化するが動く)

---

## 計測 (成功判定)

- [ ] Stage 0 完了時、`logger.info("startup", extra={"event":"startup"})` が JSON line で
      `%APPDATA%\aya-afi\logs\app.log` に 1 行出力されるスモークテスト pass
- [ ] `test_logging_redaction.py`: 環境変数 `GEMINI_API_KEY=xxx` 設定後、
      `logger.info("x", extra={"token":"xxx"})` のログ出力に "xxx" が含まれない
- [ ] 30 日分のローテを mock time でシミュレート → 31 日目に最古ファイル削除確認
- [ ] UI のログフォルダを開くボタンで実際にエクスプローラが起動する

---

## 実装メモ (Stage 0 実装時に参照)

```python
# src/aya_afi/utils/logging.py (スケッチ)
import logging, os, re
from logging.handlers import TimedRotatingFileHandler
from pythonjsonlogger.json import JsonFormatter
from aya_afi.utils.paths import get_logs_dir

def setup_logging(level: str = "INFO", redact_patterns: list[str] | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    log_path = get_logs_dir() / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        filename=log_path, when="midnight", backupCount=30, encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(event)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
    if redact_patterns:
        handler.addFilter(SecretRedactionFilter(redact_patterns))
    root.addHandler(handler)
```
