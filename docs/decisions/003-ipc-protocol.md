# ADR-003: IPC プロトコル (Tauri ↔ Python sidecar)

- **日付**: 2026-04-22
- **ステータス**: 承認済 (2026-04-22)
- **Revisions**: 2026-04-22 ADR-005 連動で Request.params に `idempotency_key` (= post_target.id) を必須化
- **決定者**: kyohei
- **関連**: [ADR-001](001-initial-architecture.md), [ADR-002 Stage 1](002-mvp-scope.md)

---

## Context (問題)

ADR-001 で Tauri ↔ Python の通信は **JSON over stdin/stdout** と決めた。
Stage 1 (Walking Skeleton) 着手前に、具体プロトコル (メッセージ型 / エラー処理 /
型自動同期) を確定する必要がある。型ズレは v0.1 最大のストレス源になるため、
**Pydantic を Single Source of Truth** とし TS 側は自動生成する。

## Decision (結論)

### プロトコル: NDJSON over stdin/stdout

- 1 行 = 1 JSON メッセージ (改行 `\n` で区切り)
- UTF-8、BOM なし
- 各メッセージは pydantic モデル `.model_dump_json()` で生成

### メッセージ型 (3 種)

#### Request (Tauri → Python)

```python
class Request(BaseModel):
    schema_version: int = 1
    request_id: str                 # UUID v4、Response で紐付け
    action: Literal[
        "generate_post",
        "publish",
        "open_note_compose",
        "list_drafts",
        "health_check",
        # ...
    ]
    params: dict[str, Any]
    timeout_sec: float = 30.0       # LLM は 60 推奨
```

#### Response (Python → Tauri)

```python
class Response(BaseModel):
    schema_version: int = 1
    request_id: str
    ok: bool
    data: dict[str, Any] | None = None
    error: ErrorInfo | None = None  # ok=False 時のみ

class ErrorInfo(BaseModel):
    type: str                       # "rate_limit" / "api_down" / "validation" 等
    message: str                    # ユーザー表示用
    detail: str | None = None       # スタック、internal 向け
    retry_after_sec: float | None = None
```

#### Event (Python → Tauri、非同期通知)

```python
class Event(BaseModel):
    schema_version: int = 1
    event_type: Literal[
        "progress",                 # 進捗更新
        "sidecar_ready",
        "sidecar_error",
        "heartbeat",
    ]
    payload: dict[str, Any]
```

### TS 型自動生成

- **生成元**: `src/aya_afi/ipc/protocol.py` (pydantic)
- **生成先**: `ui/src/types/generated/ipc.ts`
- **生成ツール**: `datamodel-code-generator` (pydantic → JSON Schema → TS)
- **自動実行タイミング**:
  - `pre-commit` hook (`protocol.py` に差分あれば生成)
  - `pnpm dev` 起動時の preflight
  - CI で `git diff --exit-code ui/src/types/generated/` (生成物がコミットされてなければ落とす)
- **生成スクリプト**: `scripts/gen_ts_types.py`

### エラー伝播

- Python 側: 例外を `ErrorInfo` に変換して Response で返す
  - カスタム例外階層: `AyaAfiError` → `RateLimitError` / `APIDownError` / `ValidationError` 等
  - シークレットは `SecretRedactionFilter` でマスク (ADR-008 参照)
- Tauri 側: `ErrorInfo.type` でエラーダイアログ内容を分岐

### バージョン互換性

- `schema_version` を全メッセージ必須
- 起動直後に Tauri → Python で `health_check` Request を送り、
  `Response.data["protocol_version"]` を確認。不一致なら即終了 + エラーダイアログ
- 将来のスキーマ変更: バージョンを上げつつ旧バージョンを N 版分サポート (現時点は v1 のみ)

### タイムアウト / キャンセル

- デフォ 30 秒、LLM 呼び出しは 60 秒 (`Request.timeout_sec` で個別指定)
- Tauri から `cancel` Request (同じ request_id) で中断可能
- Python 側: `asyncio.CancelledError` で応答し、副作用のロールバック

### バイナリデータ (画像)

- **JSON に載せない**。`params` には画像ファイルパスを渡し、Python 側で読み込む
- 妻 PC の画像パスは ASCII 外文字を含む可能性 → Python 側で一時コピー (ADR-002 Stage 3 失敗モード参照)

### heartbeat

- Python 側から 10 秒間隔で `Event(event_type="heartbeat")` を送信
- Tauri 側: 30 秒以上来なければ「sidecar 死亡」と判定 → 再起動 (ADR-001 Failure Modes)

---

## Alternatives 検討

### 案 A (採用): NDJSON over stdin/stdout + pydantic + 型自動生成
- ✅ 実装最シンプル、Tauri sidecar 機能とネイティブ相性
- ✅ pydantic が全言語の型の正になる
- ⚠ 大きなバイナリを載せると遅い (対策: パス渡し)

### 案 B: gRPC
- ✅ 型安全性が高い、多言語
- ❌ 重装備 (proto 管理、サーバー起動)、localhost 使用には過剰

### 案 C: Unix Domain Socket / Named Pipe
- ✅ stdin/stdout より速い
- ❌ Windows / macOS / Linux で API が異なり煩雑

### 案 D: HTTP over localhost
- ✅ ツール充実、OpenAPI 併用可
- ❌ ポート衝突、プロセス寿命と HTTP サーバー寿命の不一致が面倒

### 案 E: MessagePack over stdin/stdout
- ✅ バイナリ効率良い
- ❌ 人間が目視デバッグできない、Stage 1 で動かしづらい
- ⚠ NDJSON で困ったら後から切替可能 (pydantic は両対応)

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| JSON パース失敗 | request_id 不明 | 相関不可、最小 ErrorInfo (type="parse") を固定 request_id "00000000..." で送る |
| schema_version 不一致 | プロトコル齟齬で全機能破綻 | 起動時 handshake で即検知 → ダイアログ + 終了 |
| 巨大 JSON (画像バイナリ載せ) | stdin 詰まり | JSON にバイナリ載せ禁止ルール (パス渡し)。pytest でサイズ上限検証 |
| stdin バッファ溢れ | 応答停止 | 各行 1MB 上限、超過は分割 Event で送る |
| cancel 時の副作用ロールバック忘れ | データ不整合 | SQLite トランザクション + `asyncio.shield` でクリティカル部分保護 |
| 型自動生成の失敗 | ビルド破綻 | pre-commit / CI で早期検出。生成スクリプト自体の pytest 必須 |
| heartbeat 欠落 = 誤検知で強制再起動 | UX 劣化 | 閾値 30 秒 (heartbeat 10 秒の 3 倍)。LLM 呼び出し中は heartbeat 継続 (別タスク) |

---

## ロールバック手順

1. **NDJSON が遅い**: MessagePack に切替 (pydantic は両対応、serialize 1 行変更)
2. **stdin/stdout が不安定**: Tauri のローカル Unix-like ソケットに切替 (Tauri v2 の sidecar 機能拡張待ち)
3. **型自動生成が安定しない**: 手動同期に戻す + CI でスキーマ差分チェックのみ維持

---

## 計測 (成功判定)

- [ ] Stage 1 完了時、`generate_post` Request → Response の往復が TypeScript 側から呼べる
- [ ] `test_ipc_contract.py`: 全 action の Request/Response ラウンドトリップ
- [ ] `test_schema_version.py`: schema_version 不一致時に handshake が失敗する
- [ ] CI で `git diff --exit-code ui/src/types/generated/` が緑 (生成物の同期確認)
- [ ] 大画像 (5MB × 4 枚) をパス渡しで送っても IPC が詰まらない
- [ ] pydantic モデル 1 フィールド追加 → 次の `pnpm dev` で TS 型に反映される

---

## 実装メモ (Stage 1 実装時に参照)

```python
# src/aya_afi/ipc/server.py (スケッチ)
async def run_server():
    async for line in read_stdin_lines():
        try:
            req = Request.model_validate_json(line)
        except ValidationError as e:
            write_response(ErrorResponse(type="parse", message=str(e)))
            continue
        handler = DISPATCH[req.action]
        try:
            data = await asyncio.wait_for(handler(req.params), timeout=req.timeout_sec)
            write_response(Response(request_id=req.request_id, ok=True, data=data))
        except Exception as e:
            write_response(Response(
                request_id=req.request_id, ok=False,
                error=ErrorInfo(type=classify(e), message=str(e)),
            ))
```
