# ADR-005: 投稿履歴データモデル + 整合性保証

- **日付**: 2026-04-22
- **ステータス**: 承認済 (2026-04-22)
- **決定者**: kyohei
- **関連**: [ADR-001](001-initial-architecture.md), [ADR-002 Stage 5](002-mvp-scope.md)

---

## Context (問題)

SNS 投稿と DB 書込は**別トランザクション**になる。以下のリスクが存在:

1. **二重投稿**: SNS 投稿成功 → DB 書込失敗 → 再試行で二重投稿 → 妻のフォロワー信頼失墜 + アフィ規約違反リスク
2. **孤児投稿**: SNS 投稿中に sidecar クラッシュ → DB に記録なし → 「posted のはずなのに履歴に出ない」
3. **part 投稿の扱い**: Threads 成功 / Bluesky 失敗 → どう表示し、どうリトライするか
4. **妻の「もう 1 回押しちゃった」**: 同じ商品を短時間で再投稿 → 二重投稿

銀行振込と同じ**分散トランザクション問題**。2-phase commit は SNS 側に prepare フェーズがないので不可能。代わりに **Write-first + idempotency key + 起動時リカバリ** で解決する。

Stage 5 着手前に本 ADR で決定する。Stage 1 (IPC) にも **post_target.id = idempotency key** が影響するため、Stage 5 より早く参照される。

## Decision (結論)

### テーブル設計 (SQLAlchemy + Alembic)

#### `posts` (投稿の親、1 商品に対する 1 投稿セット)

| 列 | 型 | 説明 |
|---|---|---|
| `id` | TEXT PK | UUID v4 |
| `created_at` | TIMESTAMP | 作成時刻 |
| `updated_at` | TIMESTAMP | 最終更新 |
| `product_url` | TEXT | Amazon / 楽天の商品 URL |
| `product_title` | TEXT | 商品名 (アフィ API から取得) |
| `affiliate_link` | TEXT | もしも経由のアフィ URL |
| `generated_text_markdown` | TEXT | LLM 生成オリジナル (編集前) |
| `final_text_markdown` | TEXT | 妻が編集した最終版 |
| `image_paths` | TEXT (JSON) | 添付画像パスの配列 |
| `pulldown_options` | TEXT (JSON) | フック / トーン / 絵文字量 の選択値 |
| `status` | TEXT | draft / queued / posting / posted / partial / failed |
| `dry_run` | INTEGER | 0 / 1 |

#### `post_targets` (SNS 別の投稿結果、posts 1 : N)

| 列 | 型 | 説明 |
|---|---|---|
| `id` | TEXT PK | UUID v4 = **idempotency key** |
| `post_id` | TEXT FK | `posts.id`, ON DELETE CASCADE |
| `sns` | TEXT | threads / bluesky / note |
| `status` | TEXT | pending / posting / posted / failed |
| `attempted_count` | INTEGER | 0 スタート、試行ごとに +1 |
| `posted_at` | TIMESTAMP NULL | 成功時のタイムスタンプ |
| `sns_post_id` | TEXT NULL | Threads/Bluesky で発行された ID |
| `sns_post_url` | TEXT NULL | 投稿の公開 URL |
| `last_error_type` | TEXT NULL | rate_limit / api_down / validation 等 |
| `last_error_message` | TEXT NULL | ユーザー表示用 |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |
| UNIQUE | (post_id, sns) | 同じ post に同じ SNS 2 回は禁止 |

#### `drafts` (LLM 生成直後の自動保存、90 日保持)

| 列 | 型 | 説明 |
|---|---|---|
| `id` | TEXT PK | UUID v4 |
| `post_id` | TEXT FK NULL | 対応する post がある場合 (ない場合もあり、下書きのみ) |
| `created_at` | TIMESTAMP | |
| `content_markdown` | TEXT | 生成テキスト |
| `file_path` | TEXT | `drafts/<ts>-<slug>.md` ファイルのパス |
| `expires_at` | TIMESTAMP | 作成から 90 日後、自動削除 |

### 状態マシン

```
posts:
  ┌─────────────────────────────┐
  │ draft                         │  (UI で編集中)
  └────────┬────────────────────┘
           │ 投稿ボタン押下
           ↓
  ┌─────────────────────────────┐
  │ queued                        │  (sidecar が処理開始前)
  └────────┬────────────────────┘
           │ sidecar が pick up
           ↓
  ┌─────────────────────────────┐
  │ posting                       │  (SNS 投稿中)
  └────────┬────────────────────┘
           │ 全 target 完了 (結果集計)
    ┌──────┼───────────────┐
    ↓      ↓               ↓
  posted  partial         failed
  (全成功) (一部成功)       (全失敗)


post_targets (SNS 1 つあたり):
  pending → posting → posted
                    ↓ (失敗)
                  failed (attempted_count++)
                    ↓ (UI からリトライ押下)
                  posting → posted or failed
```

### Write-first パターン (手順書)

1. **「投稿」ボタン押下 (UI → Tauri → Python)**
2. **DB 先書き (トランザクション内)**:
   - `posts` を `status=queued` で INSERT
   - 対象 SNS ごとに `post_targets` を `status=pending` で INSERT
   - commit
3. **sidecar が pick up**: `posts.status = posting` に UPDATE
4. **各 SNS について順次処理**:
   a. `post_target.status = posting` + `attempted_count++` を UPDATE + commit (先書き)
   b. SNS API 呼び出し。**idempotency key = `post_target.id`** を渡す
      - Threads: `client_token` パラメタに UUID
      - Bluesky: atproto に idempotency 機構なし → 後述の Layer 1 防御に頼る
      - note: クリップボード操作のみ、API 呼び出しなし
   c. **成功**: `sns_post_id`, `sns_post_url`, `posted_at`, `status=posted` で UPDATE
   d. **失敗**: `last_error_type`, `last_error_message`, `status=failed` で UPDATE
5. **集計**: 全 `post_targets` の状態から `posts.status` を算出 (posted / partial / failed)

### 起動時リカバリ (クラッシュ復旧)

sidecar 起動時、必ず以下を実行:

```python
# 疑似コード
async def recover_on_startup(session):
    orphans = session.query(Post).filter(
        Post.status.in_(["queued", "posting"])
    ).all()
    for post in orphans:
        targets_posting = [t for t in post.targets if t.status == "posting"]
        if targets_posting:
            # 前回クラッシュ中の可能性大。UI に「前回未完了」通知を送る
            emit_event("startup_orphan_detected", post_id=post.id, ...)
        # 自動で再投稿はしない (二重投稿リスクのため)。ユーザー判断を待つ。
```

UI 側:
- 「前回未完了の投稿が 1 件あります」ダイアログ表示
- [確認する (詳細画面へ)] [あとで] ボタン
- 詳細画面: 「Threads は成功、Bluesky は不明です」と表示
- ユーザーが SNS を自分の目で確認して [再試行 / 破棄] 選択

**重要**: アプリは**絶対に自動再投稿しない**。孤児レコードは必ず人間判断を挟む。

### 二重投稿防止 (3 層防御)

#### Layer 1: アプリ内チェック (一次)

「投稿」ボタン押下時:

```python
recent_duplicates = session.query(Post).filter(
    Post.product_url == current_url,
    Post.status.in_(["queued", "posting", "posted", "partial"]),
    Post.created_at > now() - timedelta(minutes=5),
).all()
```

1 件以上あれば:
- ダイアログ「最近同じ商品を投稿しました。続行しますか?」
- 過去投稿の `sns_post_url` を一覧表示
- 妻が明示的に OK した場合のみ続行

#### Layer 2: SNS API 側 (二次、可能な場合)

- **Threads**: `client_token` (UUID) を渡すと同 token の投稿はサーバー側でマージ
  → `post_target.id` を client_token として使う
- **Bluesky**: atproto に idempotency なし → Layer 1 でカバー
- **note**: 手動投稿、対象外

#### Layer 3: 定期 / 起動時チェック (三次)

- sidecar 起動時 + 定期 (1 時間おき) に `posting` で 30 分以上経過のレコードを検知
- 「goner」とマークし、ユーザーに通知

### `partial` 投稿の扱い

- UI で該当投稿に「一部失敗」バッジ表示
- 詳細画面で「Threads: ✅ 投稿済」「Bluesky: ❌ レート制限」「note: ― 未投稿」
- **[失敗した SNS だけリトライ]** ボタンを提供
  - リトライ時は `post_target.status == posted` のものは**絶対にスキップ** (再投稿防止)
  - `post_target.status in (pending, failed)` のみを再処理

### drafts クリーンアップ

- 起動時 + 毎日 1 回、`drafts.expires_at < now()` のレコードを削除
- 対応するファイル (`drafts/<id>.md`) も削除
- UI で妻が「お気に入り」フラグを立てた draft は削除対象外 (v0.2 以降の拡張として想定)

---

## Alternatives 検討

### 案 A (採用): Write-first + state machine + idempotency key + 起動時リカバリ
- ✅ 整合性の穴を起動時 hook で塞ぐ
- ✅ 二重投稿を 3 層で防御
- ⚠ 複雑度中、pytest で網羅的にカバー必須

### 案 B: fire-and-forget (DB は事後記録のみ)
- ❌ クラッシュ時に履歴消失、二重投稿検知不可
- → 却下

### 案 C: SNS 投稿優先 → DB は非同期で追記
- ❌ DB 失敗時の履歴欠落、整合性崩壊
- → 却下

### 案 D: 2-phase commit (prepare / commit)
- ❌ SNS API 側に prepare フェーズなし、実現不可能
- → 却下

### 案 E: Outbox パターン (投稿要求を別テーブルに溜めて worker が処理)
- ✅ より堅牢
- ⚠ 妻 PC ローカル 1 プロセスには過剰、複雑度増
- → v1.0 以降で検討余地

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| **SNS 投稿成功 + DB 書込失敗** | 二重投稿の温床 | Write-first で先に DB、次に SNS。順序逆転させない |
| **SNS 投稿前に sidecar クラッシュ** | 投稿されてないが posting 状態残る | 起動時リカバリで検知 → 人間判断 |
| **SNS 投稿中にクラッシュ** | 投稿成功/失敗不明 | 起動時リカバリ + ユーザーに SNS 画面で確認依頼 |
| 妻の二重押し | 二重投稿 | Layer 1 で 5 分以内の同商品ブロック |
| Layer 1 をすり抜けた二重投稿 | フォロワーに重複表示 | Layer 2 (client_token) でサーバー側 dedup (Threads のみ) |
| `partial` 投稿の誤リトライで成功済みに再投稿 | 二重投稿 | リトライは `status != posted` のみ対象、テストで固定 |
| SQLite ロック競合 (sidecar 多重起動) | DB 破損 | sidecar は単一プロセス保証 (Tauri 側で `filelock`) |
| drafts ファイル肥大 | ディスク圧迫 | 90 日自動削除 + ユーザーが手動削除可能 |
| 起動時リカバリで orphan が積み重なる | UI がうるさい | 一度ユーザーが「破棄」した orphan は再通知しない |

---

## ロールバック手順

1. **Layer 1 (5 分ブロック) が厳しすぎる**: 期間を 1 分 or 30 秒に短縮
2. **idempotency key が役立たない**: Threads 側の実装が無効 or 変更 → Layer 1 のみに頼る
3. **起動時リカバリでパフォーマンス問題**: `posts.status` に index、古い orphan は 7 日で自動破棄

---

## 計測 (成功判定)

### Stage 5 DoD

- [ ] `posts` / `post_targets` / `drafts` テーブルが alembic で生成
- [ ] pytest ケース:
  - Write-first: DB 書込後に SNS API を mock で呼び、成功/失敗両パスで状態が正しく遷移
  - 起動時リカバリ: `status=posting` のレコードが残った状態で起動 → UI イベントが飛ぶ
  - 二重投稿防止 Layer 1: 同じ URL で 2 回「投稿」押下 → 2 回目がブロックされる
  - partial リトライ: `posted` の SNS は再実行されない
  - drafts クリーンアップ: expires_at < now のレコード削除
- [ ] 実 SNS (dry-run) で 1 商品 3 SNS の full flow が通る
- [ ] クラッシュシミュレーション: 投稿中に sidecar を kill → 次回起動で orphan が UI に出る

### 運用後 (v0.1 リリース 1 ヶ月)

- 二重投稿: 0 件 (妻のフォロワーからの指摘 0 件)
- orphan レコード残存: 1 件/週 以下
- partial 投稿発生率: 5% 未満 (API 失敗率の目安)

---

## 影響範囲

- **ADR-003 (IPC)**: Request に `post_target.id` を含める必要あり (UI → Python の idempotency key)
- **ADR-004 (LLM)**: 影響なし
- **ADR-009 (SNS 別生成エンジン)**: 影響軽微、呼び出しインターフェースは本 ADR が上位
- Stage 1 (Walking Skeleton) 時点では `status` を簡易に `posted` 固定で進めてもよい、Stage 5 で本格実装

---

## 実装メモ (Stage 5 実装時に参照)

```python
# src/aya_afi/storage/service.py (スケッチ)
async def publish_post(
    session: AsyncSession,
    post_id: str,
    targets: list[SnsKind],
    poster: PosterFacade,
) -> PublishResult:
    post = await session.get(Post, post_id)
    post.status = "posting"
    await session.commit()

    for sns in targets:
        target = await _get_or_create_target(session, post_id, sns)
        target.status = "posting"
        target.attempted_count += 1
        await session.commit()

        try:
            result = await poster.post(
                sns=sns,
                text=post.final_text_markdown,
                images=post.image_paths,
                idempotency_key=target.id,
            )
            target.status = "posted"
            target.sns_post_id = result.id
            target.sns_post_url = result.url
            target.posted_at = datetime.now(UTC)
        except PosterError as e:
            target.status = "failed"
            target.last_error_type = e.kind
            target.last_error_message = str(e)
        await session.commit()

    post.status = _aggregate_status(post.targets)
    await session.commit()
    return PublishResult.from_post(post)
```
