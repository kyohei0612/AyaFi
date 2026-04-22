# ADR-001: 初期アーキテクチャ (Tauri + Python sidecar)

- **日付**: 2026-04-22
- **ステータス**: 承認済み (2026-04-22、社外レビュー反映済み)
- **決定者**: kyohei
- **関連**: (これが最初の ADR)
- **Revisions**: 2026-04-22 社外エンジニアレビューを反映 (本 ADR 末尾の Revisions 節参照)

---

## Context (問題)

aya-afi-ver1 は、妻 (非エンジニア) が Windows ローカルで半自動 SNS アフィリエイト
投稿を行うためのデスクトップアプリ。以下を全て満たす必要がある。

- **配布形態**: 単一 `.exe` で妻 PC (Intel i7-10750H / RAM 16GB / RTX 2070 / Win64) に
  インストール可能であること。Python / Node の別途インストール不要。
- **UI 品質**: 妻が毎日使うため、モダンで違和感のない見た目 / レスポンス
- **連携先の多さ**: 楽天 Web Service API / もしも API / Gemini API / Threads Graph API /
  Bluesky (atproto) / note (ブラウザ自動化でペースト)
- **将来拡張**: SNS 追加、LLM 切替 (Gemini → Ollama ローカル)、プルダウン追加が頻繁
- **エンジニアリング憲章 (プロチェック 13 ルール) 準拠**: 特に 1 ファイル 300 行 /
  pytest / mypy strict / 構造化ログ / pydantic / SQLite

## Decision (結論)

**Tauri (Rust + WebView) をシェル、Python 3.12 sidecar をビジネスロジック** とする
ハイブリッド構成を採用する。

### 構成図

```
┌─────────────────────────────────────────────────┐
│ Tauri Shell (Rust) : ウィンドウ / IPC / ショートカット │
│  ┌───────────────────────────────────────────┐ │
│  │ WebView: React + TypeScript UI             │ │
│  │  (入力フォーム / プルダウン / エディタ / 投稿ボタン) │ │
│  └───────────────────────────────────────────┘ │
│             ↕ Tauri invoke (JSON)               │
└────────────┬────────────────────────────────────┘
             │ stdin/stdout (JSON, pydantic 型付き)
             ↓
┌─────────────────────────────────────────────────┐
│ Python sidecar (PyInstaller 埋め込み)            │
│  ├─ affiliate/ (もしも / 楽天)                    │
│  ├─ llm/      (Gemini / Claude / Ollama)         │
│  ├─ poster/   (Threads / Bluesky / note)         │
│  ├─ storage/  (SQLite + alembic)                 │
│  └─ config/   (pydantic-settings, md ローダ)      │
└─────────────────────────────────────────────────┘
```

### 言語役割

| レイヤー | 技術 | 責務 |
|---|---|---|
| UI | React + TS | フォーム / バリデーション / 表示のみ。ロジック持たない |
| Shell | Tauri (Rust) | ウィンドウ管理 / 起動ショートカット / sidecar 起動監視 / ファイル IO |
| 本体 | Python sidecar | アフィ API / LLM / SNS 投稿 / 永続化 / 設定読み込み |

### ディレクトリ配置

```
aya-afi-ver1/
├── src/aya_afi/          # Python 本体 (プロチェック ルール1: src/ = 本体)
│   ├── affiliate/        # moshimo.py / rakuten.py
│   ├── llm/              # base.py (Protocol) / gemini.py / claude.py / ollama.py
│   ├── poster/           # threads.py / bluesky.py / note.py
│   ├── storage/          # models.py (pydantic) / db.py (SQLite)
│   ├── config/           # settings.py (pydantic-settings) / md_loader.py
│   ├── ipc/              # Tauri との JSON プロトコル
│   └── __init__.py
├── src-tauri/            # Rust: tauri.conf.json + src/main.rs (最薄)
├── ui/                   # React + Vite + TS
├── tests/                # pytest (Python)
├── scripts/              # python -m aya_afi.cli ... 最薄エントリ
├── config/               # 利用者編集可能な md / yaml
├── docs/
├── secrets/
└── <root files: README.md, CLAUDE.md, pyproject.toml, .gitignore>
```

---

## Alternatives 検討

### 案 A (採用): Tauri + Python sidecar
- ✅ Python エコシステム全活用 (楽天 SDK、playwright、pydantic 等)
- ✅ React 経由でモダン UI (shadcn/ui 等流用可)
- ✅ 最終 exe 20-40MB 程度 (Python 同梱含む)
- ⚠ 二言語並行保守 (ただし Rust 側は最薄)
- ⚠ sidecar プロセス管理が必要 (停止検知、再起動)

### 案 B: Flet 単体 (Python + Flutter)
- ✅ Python 単一言語で最速実装
- ✅ exe 化は `flet pack` 一発
- ❌ exe 80-120MB (Flutter runtime 同梱)
- ❌ UI は Flutter 流儀。shadcn/Radix 等のモダン React エコシステム使えない
- ❌ デザイン細部調整の余地が狭い

### 案 C: Electron + Node.js
- ✅ 情報量最多、エコシステム成熟
- ❌ exe 150MB+、メモリ 200MB+ (妻 PC でも動くが重い)
- ❌ Python 資産を使うなら結局 sidecar が必要 → 案 A と同じ複雑度、exe だけ重くなる

### 案 D: PyQt / PySide6
- ✅ Python 単一
- ✅ 枯れている
- ❌ UI モダン化に相当の CSS/QSS 調整必要
- ❌ exe 60-100MB

### 選定理由

案 A は「**UI 品質**」と「**Python エコシステム活用**」と「**exe 軽量**」を同時に成立
させられる唯一の選択肢。二言語保守コストは Rust 側を IPC + window 管理に絞れば
許容範囲 (プロチェック ルール 1「エントリは最薄」の考え方と一致)。

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| Sidecar プロセス起動失敗 | UI 全機能停止 | Tauri 側で起動失敗検知 → エラーダイアログ + ログ提出導線 |
| Sidecar ランタイム中クラッシュ | 操作途中で停止 | tenacity で最大 3 回自動再起動、失敗時は構造化ログ `event=sidecar_crash` |
| PyInstaller バンドル漏れ | 妻 PC で起動不能 | CI で PyInstaller ビルド後、smoke test (sidecar ping) 必須 |
| **PyInstaller `_MEIPASS` パス問題** | 凍結環境で config/SQLite/alembic スクリプトのパス解決失敗、妻 PC でのみ再現する厄介バグ | `src/aya_afi/utils/paths.py` を作り `sys.frozen` を判定して dev/frozen 両対応の解決関数を提供。全パス解決をこのモジュール経由に統一。テストで frozen 環境をモック |
| **DB マイグレーション忘れ** | スキーマ変更時に妻 PC でエラー | sidecar 起動時に `alembic upgrade head` を自動実行 (初回起動含む)。失敗時は明示エラー + ロールバック可能な状態 |
| SmartScreen 警告で妻が実行しない | v0.1 配布で詰む | README に手順明記。v0.2 以降で署名検討 (別 ADR) |
| IPC プロトコル非互換 | UI ↔ sidecar バージョン不整合 | pydantic メッセージに `schema_version` 必須、不整合時は明示エラー |
| API キー漏洩 | アフィ / LLM 悪用 | `%APPDATA%\aya-afi\secrets\.env` に分離、UI 表示時はマスク |
| 楽天 / もしも / Gemini のレート超過 | 連続投稿時に失敗 | アプリ側でレートリミッタ (asyncio + tenacity) を必ず挟む |
| note 自動投稿が規約違反扱いされる | note アカウント凍結 | 自動投稿しない。文章ペーストのみ。投稿ボタンは人手 (実装方式は ADR-006 で決定) |
| **生成済み文章が SNS API 失敗で消える** | 妻の作業が無駄、心理的ストレス | LLM 生成直後に `%APPDATA%\aya-afi\drafts\<timestamp>-<slug>.md` に自動保存。SNS 投稿成否と独立。dry-run 時も保存 |
| **ユーザー設定破壊** | 妻が `config/` の md を壊すと動かなくなる | **config 2 段構え**: exe 同梱の読取専用デフォ (`sys._MEIPASS/config/`) + APPDATA のユーザー版 (`%APPDATA%\aya-afi\config\`)。起動時はユーザー版を優先読込、無ければデフォからコピー。UI に「デフォルトに戻す」ボタン |

---

## ロールバック手順

1. **Tauri UI が動かない場合**: sidecar 単体の CLI モードにフォールバック
   ```powershell
   python -m aya_afi.cli post --link "<url>" --sns threads --dry-run
   ```
2. **Sidecar が動かない場合**: Tauri 単体で「下書き保存モード」に切り替え、
   生成テキストを markdown ファイルとしてエクスポート可能にする (投稿機能オフ)
3. **両方ダメな場合**: `config/*.md` は全て人が読める markdown なので、
   プロンプトを手動で Gemini / Claude ブラウザ版にコピペして使える
   (つまりツール死んでも業務は止まらない設計)

---

## 計測 (成功判定)

v0.1 リリース受け入れ基準:

- [ ] 妻が単独で「商品 URL 入力 → プルダウン選択 → 文章確認 → 3 SNS 投稿」を完遂
- [ ] dry-run 連続 10 回が全てエラーなし (楽天 / もしも / Gemini / Threads / Bluesky)
- [ ] `pytest -q` カバレッジ 70% 以上で green
- [ ] `mypy --strict` + `ruff` + `black --check` が CI で green
- [ ] PyInstaller ビルド + Tauri bundler で `.msi` or `.exe` が生成される
- [ ] 妻 PC (aya) で実際にインストール → 1 商品投稿完遂

運用計測 (v0.1 リリース後):
- 投稿成功率: `storage/` の投稿履歴テーブルから集計
- API 失敗率 / リトライ回数: 構造化ログを集計
- クリック / 成果 は v0.2 の管理画面で可視化 (本 ADR の範疇外)

---

## 影響範囲

新規プロジェクトにつき既存システムへの影響なし。ただし以下の**外部準備**が必要:

| 準備項目 | 状態 | 担当 |
|---|---|---|
| もしもアフィリエイト会員登録 | 未 | kyohei / 妻 |
| もしも: Amazon プロモーション提携申請 | 未 | 妻 |
| もしも: 楽天プロモーション提携申請 | 未 | 妻 |
| 楽天 Web Service アプリ ID 発行 | 未 | kyohei |
| Google AI Studio で Gemini API キー発行 | 未 | kyohei |
| Meta 開発者登録 + Threads アプリ作成 | 未 | kyohei |
| Bluesky アカウント作成 + App Password 発行 | 未 | kyohei / 妻 |
| note アカウント作成 | 未 | 妻 |

---

## 次の ADR (予定)

- **ADR-002**: MVP スコープ確定 (v0.1 で何を出すか、何を後回しにするか)
- **ADR-003**: IPC プロトコル定義 (Tauri ↔ Python の JSON メッセージ型 / `datamodel-code-generator` で Pydantic → TS 型自動生成)
- **ADR-004**: LLM プロバイダ抽象化 (Strategy パターン / Protocol)
- **ADR-005**: 投稿履歴データモデル (SQLite スキーマ + alembic)
- **ADR-006**: note 自動化の規約適合性 (法務的検討)
- **ADR-007**: CI/CD パイプライン (GitHub Actions / 自動 .exe リリース)
- **ADR-008**: ロギング戦略 (stdlib logging + python-json-logger + 日次ローテ)
- **ADR-009**: SNS 別コンテンツ生成エンジン (プラットフォーム特性反映、プロンプト注入、dry-run バリデーション)
- **ADR-010**: エラーハンドリング UX (sidecar 自動リカバリの見せ方、妻パニック防止)
- **ADR-011**: 配布署名戦略 (SmartScreen 対策、段階的署名導入)

---

## Revisions

### 2026-04-22: 社外エンジニアレビュー反映

社外エンジニア (プロ評価) から以下指摘を受領、反映内容を本節に記録。

#### 反映済み (本 ADR に追記)

1. **PyInstaller `_MEIPASS` パス問題 (指摘②)**
   - 失敗モード表に追加
   - 対処: `src/aya_afi/utils/paths.py` を新規モジュールとして定義。`architecture.md` にも責務を追加
   - 理由: 凍結環境で `config/`, SQLite, alembic スクリプトのパスが temp に展開されるため、
     `sys.frozen` と `sys._MEIPASS` を見て dev/frozen 両対応の解決関数を提供する必要あり

2. **DB 自動マイグレーション (指摘④)**
   - 失敗モード表に追加
   - 対処: sidecar 起動シーケンスの最初に `alembic upgrade head` を実行
   - 理由: 妻にコマンド操作を要求しない設計方針と整合

3. **エントリポイント明確化 (指摘⑤)**
   - `scripts/sidecar.py` (Tauri からの spawn 対象、最薄)
   - `scripts/cli.py` (CLI フォールバック用、最薄)
   - 両方とも `src/aya_afi/ipc/server.py` および `src/aya_afi/cli/` に処理を委譲
   - プロチェック rule 1「scripts/ は CLI エントリのみ、ロジックは src/」と整合

4. **TS ↔ Pydantic 型自動同期 (指摘⑦)**
   - ADR-003 (IPC プロトコル定義) で `datamodel-code-generator` or `pydantic-to-typescript` を
     採用前提と明記。CI で Pydantic モデルから TS 型を自動生成し、`ui/src/types/generated/` に配置
   - 理由: Tauri ↔ Python の JSON 型ズレは v0.1 最大のストレス源になるため先回り

#### 別 ADR に繰り越し

5. **CI/CD 自動リリース (指摘①)** → ADR-007
   - v0.1 リリース直前に別建て。GitHub Actions で `pnpm tauri build` → GitHub Releases 自動公開
   - 今は骨組みに集中するため後回し

6. **ロギング戦略 (指摘③)** → ADR-008 (方針確定済み、詳細は ADR-008 で)
   - 指摘では `loguru` 推奨だが、**プロチェック rule 6「logging モジュールのみ」に抵触** するため却下
   - 代替案: stdlib `logging` + `python-json-logger` + `TimedRotatingFileHandler` で同等機能を実現
     - 出力先: `%APPDATA%\aya-afi\logs\app.log`
     - 日次ローテ、30 日分保持
     - JSON フォーマッタで構造化ログ
   - UI にログフォルダを開くボタンを追加 (指摘③の妻向け UX 改善案は採用)
   - 最終決定: 2026-04-22 kyohei さんから「まかせる」で stdlib 案に確定

### 2026-04-22: 追加レビュー反映 (プロアドバイス 2 巡目)

1. **paths.py 実装ヒント + config 2 段構え (追加指摘①)**
   - 失敗モード表に「ユーザー設定破壊」を追加
   - `utils/paths.py` に以下関数を定義 (リファレンス実装):
     ```python
     import sys
     from pathlib import Path

     APP_NAME = "aya-afi"

     def get_app_root() -> Path:
         """exe 同梱の読取専用リソース (config デフォ、alembic スクリプト等) の基準"""
         if getattr(sys, "frozen", False):
             return Path(sys._MEIPASS)
         return Path(__file__).resolve().parents[3]

     def get_user_data_dir() -> Path:
         """書き込み可能なユーザーデータ (%APPDATA%\\aya-afi\\) の基準"""
         base = Path.home() / "AppData" / "Roaming" / APP_NAME
         base.mkdir(parents=True, exist_ok=True)
         return base

     def get_config_dir() -> Path:      return get_user_data_dir() / "config"
     def get_logs_dir() -> Path:        return get_user_data_dir() / "logs"
     def get_drafts_dir() -> Path:      return get_user_data_dir() / "drafts"
     def get_secrets_dir() -> Path:     return get_user_data_dir() / "secrets"
     def get_db_path() -> Path:         return get_user_data_dir() / "aya_afi.sqlite"

     def get_default_config_dir() -> Path:
         """読取専用デフォ (exe 同梱 or dev repo の config/)"""
         return get_app_root() / "config"
     ```
   - 初回起動時、`get_default_config_dir()` → `get_config_dir()` に md をコピー
   - 以降はユーザー版を優先、存在しないファイルだけデフォから補完

2. **型同期の pre-commit / pnpm dev 組み込み (追加指摘②)** → ADR-003 で確定
   - `.pre-commit-config.yaml` に pydantic → TS 型生成フックを追加
   - `pnpm dev` の preflight で `python scripts/gen_ts_types.py` を走らせる
   - Pydantic モデル編集時に TS 側も自動更新、ズレ不可能な状態を作る

3. **下書き自動保存 (追加指摘③)**
   - 失敗モード表に「生成済み文章が SNS API 失敗で消える」を追加
   - LLM 生成直後、投稿前に `%APPDATA%\aya-afi\drafts\<YYYYMMDD-HHMMSS>-<slug>.md` に保存
   - 投稿成否と独立。dry-run 時も保存
   - UI に「下書き一覧」タブを追加 (v0.1 スコープ内)

4. **note 実装方式 (追加指摘④)** → **2026-04-22 確定: 案 3 採用**
   - 案 1: playwright で自動入力 → 実装重、規約リスク中、堅牢性低 → 却下
   - 案 2: SendInput で Ctrl+V エミュレート → フォーカス依存で脆弱 → 却下
   - 案 3 (採用): 自動化ゼロで最安全
     - 「投稿」ボタン押下時、Threads / Bluesky に投稿 + **本文をクリップボードに自動コピー** + `drafts/` に保存
     - 「投稿」ボタンの**隣**に独立した「note で開く」ボタンを配置
     - そのボタンを押すと OS の既定ブラウザで `https://note.com/notes/new` を開く (Tauri `shell.open`)
     - 妻は開いた note タブで Ctrl+V → タイトル入力 → 投稿
   - ADR-006 は「案 3 で確定、将来 case 1 引き上げ可否を運用実績で再評価」のみ記載する短い ADR になる予定
   - 詳細 UI 配置は v0.1 実装時に調整

#### 反映不要 (既に ADR で定義済み)

7. **疎結合設計 (指摘の評価①)**: 既に本 ADR の Decision で定義済み、言及のみ
8. **ADR 文化 (指摘の評価②)**: 既にプロチェック rule 13 で必須化、言及のみ
9. **セキュリティ (指摘の評価③)**: 既に失敗モード「API キー漏洩」で対処済み
10. **LLM 抽象化 (指摘⑥)**: 既に architecture.md で `llm/base.py` Protocol を定義済み
