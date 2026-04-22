# ADR-002: MVP (v0.1) スコープ確定

- **日付**: 2026-04-22
- **ステータス**: 承認済 (2026-04-22、画像添付機能を追加)
- **決定者**: kyohei
- **関連**: [ADR-001](001-initial-architecture.md)
- **Revisions**: 2026-04-22 kyohei さんから画像添付機能 (F20) を v0.1 に追加指示、反映済み

---

## Context (問題)

ADR-001 で基礎アーキ (Tauri + Python sidecar) は確定。しかし「v0.1 で何を出すか /
何を出さないか」が曖昧なまま実装に入ると、スコープクリープで永遠に完成しない。

本 ADR で v0.1 の範囲を凍結し、実装順序 (Walking Skeleton 起点) を確定する。

## Decision (結論)

### v0.1 で出すもの (INCLUDED)

| # | 機能 | 備考 |
|---|---|---|
| F01 | 楽天 Web Service API 直接連携 | アプリ ID 発行のみで即利用可 |
| F02 | もしも API 連携 (Amazon + 楽天商品リンク発行) | 会員登録 + 提携申請必要 |
| F03 | Gemini 2.5 Flash 文章生成 (無料枠) | 1500 req/日 制限下で運用 |
| F04 | Threads Graph API 投稿 | Meta 開発者登録 + App 作成 |
| F05 | Bluesky (atproto) 投稿 | App Password で認証 |
| F06 | note コピー支援 (案 3) | クリップボードコピー + 「note で開く」ボタン |
| F07 | プルダウン 3 軸 (フック / トーン / 絵文字量) | 「指定なし」選択肢必須 |
| F08 | 下書き自動保存 + 履歴 UI | `%APPDATA%\aya-afi\drafts\`、90 日保持 |
| F09 | SQLite + alembic 自動マイグ (投稿履歴永続化) | 起動時に `upgrade head` |
| F10 | config 2 段構え + 「デフォルトに戻す」UI | exe 同梱デフォ + APPDATA ユーザー版 |
| F11 | dry-run モード (実 API 叩かず擬似投稿 + ログ) | `config/app.yaml` の `dry_run: true` |
| F12 | stdlib logging + python-json-logger + 日次ローテ | `%APPDATA%\aya-afi\logs\` |
| F13 | ショートカット起動 (タスクトレイ常駐) | Tauri global_shortcut プラグイン |
| F14 | Windows 単一 .exe 配布 | PyInstaller + Tauri bundler |
| F15 | IPC 型自動同期 (Pydantic → TS) | pre-commit + pnpm dev preflight |
| F16 | 投稿前確認ダイアログ (dry-run プレビュー) | プロチェック追加ルール 14 |
| F17 | #PR / #広告 自動付与 (ステマ規制対応) | 追加ルール 16 |
| F18 | レート制限順守 (各 API) | 追加ルール 17 |
| F19 | 二重投稿防止 (ボタン disable + lock) | 追加ルール 19 |
| F20 | **画像添付投稿** (ファイル選択式) | 2026-04-22 追加。ローカル画像を複数選択 → Threads / Bluesky に添付。note は手動 |

### v0.1 で出さないもの (NOT INCLUDED、明示却下)

| # | 機能 | 先送り先 | 理由 |
|---|---|---|---|
| X01 | Amazon PA-API 直 | v0.3 以降 | 売上 3 件/180 日達成後。もしも経由で代替 |
| X02 | ローカル LLM (Ollama) | v0.2 | Gemini 無料枠で足りるなら移行不要。実績見てから |
| X03 | **画像生成** (AI 生成画像) | 永続却下 | kyohei さん「使わんと思う」(2026-04-22)。画像添付は F20 で対応 |
| X04 | 予約投稿 / スケジューラ | v0.3 | 常駐プロセス + 冪等性設計が別 ADR 級 |
| X05 | 管理画面 (CTR / 成果分析) | v0.3 | データ蓄積してから意味が出る |
| X06 | SNS アルゴリズム解析 | v0.4 以降 | 実績蓄積 + 解析手法 ADR が必要 |
| X07 | コード署名付き exe | v0.2 | SmartScreen 警告は README で回避、まず動くものを |
| X08 | 自動アップデート (Tauri updater) | v0.2 | 配布先が妻 PC 1 台なら手動上書きで十分 |
| X09 | 多アカウント対応 (SNS 毎) | v0.3 | 妻 1 名運用で不要 |
| X10 | CI/CD 自動リリース | ADR-007 (v0.1 直前) | 個人開発段階は手動ビルドで可 |
| X11 | macOS / Linux 対応 | 永続却下 | 妻 PC / kyohei PC とも Windows 固定 |

### 実装順序 (Walking Skeleton 起点)

スコープを機能横断ではなく**縦割り (Walking Skeleton)** で着手。
まず「全レイヤー貫通の極小機能」を動かし、以後はそこに肉付けする。

#### Stage 0: リポジトリ基盤 (1-2 日)
- ディレクトリスケルトン (src/ / src-tauri/ / ui/ / tests/ / scripts/)
- `pyproject.toml` (uv + ruff + black + mypy + pytest + pydantic)
- `Cargo.toml` (Tauri v2)
- `package.json` (pnpm + vite + react + ts)
- pre-commit config (ruff + black + mypy + datamodel-code-generator)
- `utils/paths.py` (ADR-001 リファレンス実装の通り)
- `utils/logging.py` (stdlib + python-json-logger + TimedRotatingFileHandler)
- pytest スモーク 1 本 (`test_paths.py`)

#### Stage 1: Walking Skeleton (2-3 日)
**目的**: Tauri → Python → Gemini → (模擬) Threads の全レイヤーを貫通
- UI: 商品 URL 入力 1 個 + 生成ボタン + テキストエリア
- Tauri invoke 1 本: `generate_post`
- Python sidecar: stdin ループ、pydantic メッセージ、Gemini 呼び出し 1 本
- Threads 投稿は dry-run (ログ出力のみ、API 叩かない)
- **楽天/もしも/Bluesky/note は全部ハードコード or スタブで済ませる**
- Stage 1 達成基準: UI から「URL 貼る → 生成 → 画面に表示 → 投稿ボタン押下 → dry-run ログに JSON が出る」

#### Stage 2: アフィ層 (3 日)
- `affiliate/rakuten.py`: 楽天 Web Service で商品情報取得 + アフィリンク生成
- `affiliate/moshimo.py`: もしも API で Amazon / 楽天商品のアフィリンク発行
- URL 判別ロジック (amazon.co.jp / item.rakuten.co.jp で振り分け)
- pytest (モック + VCR.py で HTTP 記録)

#### Stage 3: SNS 実投稿 + 画像添付 (4-5 日)
- `poster/threads.py`: Threads Graph API 実投稿 (画像は media コンテナ → publish の 2 段階)
- `poster/bluesky.py`: atproto SDK 実投稿 (画像は blob upload → embed)
- `poster/note_clipboard.py`: クリップボードコピー + 「note で開く」Tauri invoke
  - note の画像は**妻が note 側で手動アップロード** (規約クリーンのため)
- レート制限層 (asyncio-ratelimit 系)
- dry-run / 本番 の切替
- **画像添付 UI**: ファイルピッカー (Tauri dialog) で複数画像選択、サムネ表示、並び替え / 削除
- 画像バリデーション: 拡張子 (jpg/png/webp)、サイズ (Threads 8MB / Bluesky 1MB 制限に合わせ圧縮検討)

#### Stage 4: プルダウン 3 軸 + config ローダ (2 日)
- `config/md_loader.py`: hooks.md / tones.md / emojis.md をパース
- UI に 3 プルダウン追加
- LLM プロンプトへのテンプレ注入

#### Stage 5: 永続化 (2-3 日)
- SQLite + alembic セットアップ
- `storage/models.py` (pydantic) / `storage/db.py` (sqlalchemy)
- 起動時 `alembic upgrade head` 自動実行
- 投稿履歴 UI タブ + 下書き一覧 UI タブ

#### Stage 6: 配布まわり (2 日)
- config 2 段構え (初回起動で APPDATA に展開)
- 「デフォルトに戻す」UI
- PyInstaller spec 作成
- Tauri bundler 設定 (.msi or .exe)
- 妻 PC (aya) でスモーク

#### Stage 7: 受け入れテスト + 調整 (2-3 日)
- 妻による 1 商品 × 3 SNS 実投稿
- 見つかったバグの修正
- README / runbook 執筆

### 最初に動かす「縦割り 1 本目」(Walking Skeleton 詳細)

```
[UI (React)]
  入力欄: "https://item.rakuten.co.jp/xxxx/" (ハードコードで 1 件)
  ボタン: [生成]
  ボタン: [dry-run 投稿]
  表示欄: 生成されたテキスト

[Tauri invoke("generate_post", {url})]
  ↓ sidecar.write_line({"action":"generate_post","url":"..."})
[Python sidecar]
  1. url を LLM に渡すプロンプト組立 (固定テンプレ、プルダウンなし)
  2. Gemini API 呼び出し (実 API)
  3. 結果を返す
  ↓ stdout JSON
[Tauri] UI に返却 → 表示

[UI dry-run 投稿ボタン押下]
[Tauri invoke("publish_dry_run", {text})]
[Python sidecar]
  1. logger.info(event="publish_dry_run", target="threads", text=text[:50])
  2. "ok" を返す
  ↓
[UI] "dry-run 投稿完了" トースト
```

このスケルトンで全レイヤー (UI / Tauri IPC / Python / LLM / ログ) が貫通。
以後は横方向 (SNS 追加、機能追加) に肉付けするだけ。

---

## Alternatives 検討

### 案 A (採用): Walking Skeleton → 横拡張
- ✅ 早期に全レイヤーの結合問題が発覚する
- ✅ 「動くものが 2 週目には見える」ため妻へのデモ可能、モチベ維持
- ⚠ 初期は機能がショボい (URL ハードコード等)

### 案 B: レイヤーごとに完成 (ボトムアップ)
- ❌ Python sidecar 全部作ってから UI → 最後に結合地獄
- ❌ 動くものが見えるまで 4-5 週間かかる

### 案 C: 機能単位で完成 (Threads 完結 → Bluesky 完結 → ...)
- ✅ 局所的には綺麗
- ❌ Tauri ↔ Python の結合インフラ (IPC / 型同期 / sidecar 管理) が
   最後まで固まらず、毎回書き直し発生

→ 案 A (Walking Skeleton) を採用。

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| **スコープクリープ** | 「あとこれだけ」で永遠に終わらない | 本 ADR の NOT INCLUDED 表を変更するには ADR 改訂必須。「あとこれだけ」と言われたら必ず ADR 更新 PR を先に |
| 外部準備 (API キー / もしも提携) 未完了 | Stage 2-3 で着手できない | Stage 0 開始と同時に外部準備を並行着手。Stage 1 はスタブで進む設計 |
| Gemini 無料枠 不足 | 開発中に 1500 req/日超過 | 1 投稿 = 生成 3-5 回 × 試行 → 1 日数十投稿が限界。実運用では余裕 |
| もしも API ドキュメント不足 | 実装詰まる | 詰まった時点で ADR を分岐 (楽天 Web Service 直単独で MVP を出す判断も可) |
| PyInstaller + Tauri bundle 統合が想定より複雑 | Stage 6 で時間超過 | Stage 0 でビルド疎通を先に通す (空の Python sidecar を bundle する smoke) |
| 妻受け入れテストで UX が不合格 | 出せない | Stage 3 時点で妻にデモし、Stage 4-5 で調整 |
| **画像サイズ / フォーマット非対応で投稿失敗** | 途中でエラー、妻が混乱 | 選択時にバリデーション (拡張子 / サイズ)。Bluesky 向けは Pillow で自動リサイズ |
| **画像ファイルパスが妻 PC で長すぎ / 特殊文字** | アップロード失敗 | 選択後に `utils/paths.py` 経由で一時コピー → ASCII 名に rename してから送信 |

---

## ロールバック手順

1. **Stage 6 まで行けない場合**: Stage 3 までで一度リリース候補を作り、
   「開発者 PC で動く状態」を妻 PC に手動コピー (exe なし、.venv + .node_modules 込み)
2. **どうしても note / Bluesky / もしも が間に合わない場合**:
   楽天 + Gemini + Threads の 3 層のみで v0.0.1 として先に出す。残りは追加リリース
3. **全滅した場合**: Stage 1 の Walking Skeleton だけを CLI モードとして残す。
   妻は手動で Gemini ブラウザ版にプロンプト打つ運用に戻る (=ツール導入前と同じ)

---

## 計測 (成功判定)

### v0.1 完成基準 (ADR-001 から引用 + 具体化)

- [ ] 妻が単独で「楽天 or Amazon 商品 URL → プルダウン選択 → 生成 → 編集 → 投稿 → note ペースト」を完遂
- [ ] dry-run 連続 10 回が全レイヤーエラーなし
- [ ] `pytest -q` カバレッジ 70% 以上で green
- [ ] `mypy --strict` + `ruff` + `black --check` が CI で green
- [ ] Tauri + PyInstaller で `.exe` or `.msi` が生成される
- [ ] 妻 PC (aya) で実機インストール → 1 商品投稿完遂
- [ ] 投稿履歴 DB に 1 レコード正しく記録される
- [ ] 下書きが `drafts/` に自動保存される
- [ ] **画像 2 枚を選択 → Threads / Bluesky に添付投稿できる** (note は手動対応)

### 各 Stage の DoD (Definition of Done)

各 Stage 完了時に以下を満たすこと:
- 該当機能の pytest 追加 (ロジック関数は必ず)
- mypy strict / ruff 緑
- 妻 PC ではなく開発 PC で手動動作確認済

### 運用後 (v0.1 リリース後 1 ヶ月)

- 投稿成功率: 95% 以上
- Gemini 無料枠超過: 0 日
- SNS API エラー率: 5% 未満
- 妻からのフィードバック数: 記録する (v0.2 優先度判定用)

---

## 影響範囲

ADR-001 を前提とするのみ。外部準備は ADR-001 に引き続き必要。
v0.1 直前で ADR-007 (CI/CD) を書き起こし、自動ビルド環境を整備する想定。

---

## 次の ADR (連動)

- **ADR-003**: IPC プロトコル定義 ← Stage 1 着手前に確定必須
- **ADR-004**: LLM プロバイダ抽象化 ← Stage 1 と同時に
- **ADR-005**: 投稿履歴データモデル ← Stage 5 着手前に確定必須
- **ADR-006**: note 実装方式 (案 3 確定済、短い追認 ADR) ← Stage 3 着手前に
- **ADR-008**: ロギング戦略 ← Stage 0 着手前に確定必須

---

## Revisions

### 2026-04-22: 画像添付機能追加 (F20)

kyohei さんからの指示:
> 画像付き投稿はセットでやりたいけど、最初はフォルダ選択で画像選択するみたいな機能で
> いいと思う。あとから色々投稿に付随して選択できるようにする予定。画像生成は使わん

反映:
1. **F20 を INCLUDED に追加**: ファイル選択式の画像添付 (Threads / Bluesky 対応、note は手動)
2. **X03 を「画像生成」のみに限定 + 永続却下**: 将来も AI 画像生成は入れない方針
3. **Stage 3 を 3-4 日 → 4-5 日に延長**: 画像添付 UI + アップロード処理分
4. **失敗モード 2 件追加**: 画像サイズ・フォーマット非対応、ファイルパス問題
5. **受け入れ基準に画像投稿項目を追加**
6. v0.2 以降で「商品画像を自動取得」「画像の加工 (切り抜き / 文字入れ)」等の拡張を検討
