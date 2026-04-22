# ADR-009: SNS 別コンテンツ生成エンジン

- **日付**: 2026-04-22
- **ステータス**: 承認済 (2026-04-22)
- **決定者**: kyohei
- **関連**: [ADR-004](004-llm-provider-abstraction.md), [ADR-005](005-post-history-and-integrity.md), [ADR-002 Stage 4](002-mvp-scope.md)

---

## Context (問題)

Threads / Bluesky / note は**プラットフォーム特性が全く違う**:

| SNS | 性格 | 文体 | タグ | リンク |
|---|---|---|---|---|
| Threads | 交流 / 共感 | 親しみ口調 + 質問 | 0-2 個 | **リプ欄に貼る** |
| Bluesky | 専門性 / カスタムフィード | 丁寧 + 具体スペック | 2-4 個 (正確に) | 1 つだけ、OGP で |
| note | 信頼 / 検索流入 | ブログ調、H2/H3 | 3-5 個 | 複数 OK |

**単一プロンプトで全 SNS 生成するとどれも中途半端になる**。
SNS ごとに:
- プロンプト (global.md + sns/{sns}.md + プルダウン)
- 検証ルール (文字数 / 質問誘発 / Alt テキスト 等)
- 後処理 (Threads のアフィリンク分離、note のタイトル抽出 等)

を分けて**「SNS 生成エンジン」**として設計する。将来 SNS (Misskey / Mastodon 等) を
追加しても**既存コードに手を入れずに拡張可能**な構造にする。

## Decision (結論)

### モジュール構成

```
src/aya_afi/sns_engine/
├── __init__.py
├── base.py              # SnsKind enum / Protocol / pydantic モデル
├── prompt_builder.py    # md + プルダウン → system/user prompt
├── generator.py         # LLMProvider を使って各 SNS のコンテンツ生成
├── validators/
│   ├── __init__.py
│   ├── threads.py       # Threads 特有のバリデーション
│   ├── bluesky.py
│   └── note.py
└── post_processors/
    ├── __init__.py
    ├── threads.py       # リプ用のアフィリンク投稿文を分離
    ├── bluesky.py       # 画像の Alt テキスト抽出
    └── note.py          # H1 タイトル抽出
```

投稿する `poster/` 層とは**完全分離** (ADR-001)。本 ADR は「文章を作る」責務のみ。

### Pydantic モデル (SSoT)

```python
# src/aya_afi/sns_engine/base.py
from enum import Enum
from pydantic import BaseModel, Field

class SnsKind(str, Enum):
    threads = "threads"
    bluesky = "bluesky"
    note = "note"

class PulldownOptions(BaseModel):
    hook: str | None = None       # "casual_empathy" / "number_shock" / ...
    tone: str | None = None       # "casual" / "polite" / ...
    emoji: str | None = None      # "none" / "few" / "normal" / "many"

class ValidationSeverity(str, Enum):
    error = "error"      # 投稿不可
    warning = "warning"  # 注意 (投稿は可能)
    info = "info"

class ValidationIssue(BaseModel):
    severity: ValidationSeverity
    rule_id: str         # "threads.must_have_question"
    message: str
    field: str | None = None   # "body" / "title" / "tags"

class GeneratedContent(BaseModel):
    sns: SnsKind
    title: str | None = None      # note のみ
    body: str
    tags: list[str] = []
    alt_texts: list[str] = []     # Bluesky の画像 Alt、画像と index 対応
    reply_body: str | None = None # Threads のアフィリンク用リプライ
    issues: list[ValidationIssue] = []
    model: str                    # LLM のモデル名 (記録用)
    provider: str                 # provider 名

class SnsGenerator(Protocol):
    async def generate(
        self,
        product: ProductInfo,
        options: PulldownOptions,
    ) -> GeneratedContent: ...
```

### プロンプト組立 (prompt_builder.py)

**System prompt** (LLM の役割定義):

```
{global.md の全文}

---

{sns/{sns_name}.md の全文}

---

{プルダウン選択に応じて:
 - options.hook != None → prompts/hooks.md から該当セクションを引用
 - options.tone != None → prompts/tones.md から該当セクションを引用
 - options.emoji != None → prompts/emojis.md から該当セクションを引用}

---

出力フォーマット: JSON
{
  "title": string | null,  // note のみ
  "body": string,
  "tags": string[],
  "alt_texts": string[],   // Bluesky 画像がある場合
  "reply_body": string | null  // Threads のアフィリンク投稿用
}
```

**User prompt** (商品情報):

```
商品名: {product.title}
価格: {product.price}
商品 URL: {product.url}
アフィリエイト URL: {product.affiliate_link}
カテゴリ: {product.category}
説明: {product.description}
画像枚数: {len(product.images)}

上記商品について、{sns_name} の投稿文を生成してください。
```

※ LLM 側に JSON 出力を指示 → `response_format={"type":"json_object"}` (Gemini / Claude 対応)。

### Validators (SNS 別ルール)

#### Threads

| ルール | 重要度 | チェック |
|---|---|---|
| 文字数 500 以内 | error | `len(body) <= 500` |
| **質問文が含まれる** | error | `?` or `？` or 「どう思う」等の正規表現 |
| ハッシュタグ 0-2 個 | warning | `count_hashtags(body) <= 2` |
| **親ポストにアフィリンク含まれない** | error | `not re.search(r'(amazon|rakuten|moshimo)', body)` |
| `#PR` または `#広告` が tags に含まれる | error | 規約遵守 |
| reply_body にアフィリンクがある | error | `reply_body` 内に URL 必須 |

#### Bluesky

| ルール | 重要度 | チェック |
|---|---|---|
| 文字数 300 以内 (grapheme) | error | `grapheme_count(body) <= 300` |
| ハッシュタグ 2-4 個 | warning | `2 <= count_hashtags(tags) <= 4` |
| 具体スペック 1 つ以上 | warning | 数字を含む行が 1 つ以上 |
| リンク 1 つだけ | error | URL 数 == 1 |
| 画像があれば Alt テキストあり | error | `len(alt_texts) == len(images)` |
| `#PR` 含まれる | error | |

#### note

| ルール | 重要度 | チェック |
|---|---|---|
| タイトル 32 字以内 | error | `len(title) <= 32` |
| タイトルに商品名含む | warning | fuzzy 一致 |
| H2 見出しが 2 つ以上 | warning | `##` 行数 |
| `[[ここを入力: ...]]` 空欄が含まれる | error | 正規表現で検知、最低 1 つ |
| 文字数 1500-3000 | warning | スイートスポット範囲 |
| `#PR` 含まれる | error | |

### Post-processors (後処理)

#### Threads

- `body` と `reply_body` を分離 (LLM が混ぜた場合)
- アフィリンクが `body` 内にあったら `reply_body` に移動
- `body` 末尾に `#PR` がなければ追加

#### Bluesky

- 画像数 > 0 かつ `alt_texts == []` なら LLM に再リクエスト or 警告
- タグを半角スペース区切りで body 末尾に整形

#### note

- `# タイトル` 行を body から抽出 → `title` フィールドに
- `[[ここを入力: ...]]` が 0 個なら警告
- Markdown として整形 (H2/H3 のスペーシング)

### リンク整形ルール (規約遵守で短縮しない)

**プロ指摘では「リンクの自動短縮」提案あり、だが規約違反のため却下:**

- **Amazon アソシエイト**: 短縮 URL / カスタムドメイン化禁止 (規約 5 条)
- **楽天アフィリエイト**: 短縮 URL 禁止 (利用規約)
- **もしもアフィリエイト**: もしも経由 URL は変更禁止

→ アプリは**リンクを短縮しない**。「最適化」できるのは:
- 余分なクエリパラメタの除去 (tracking 系のみ、アフィ ID は保持)
- OGP プレビューに効く位置 (Bluesky なら最後の行) への配置

これを post-processor で実施。

### マルチ SNS 生成の並列化

```python
async def generate_all(
    product: ProductInfo,
    snses: list[SnsKind],
    options: PulldownOptions,
) -> list[GeneratedContent]:
    tasks = [generate_one(product, sns, options) for sns in snses]
    return await asyncio.gather(*tasks, return_exceptions=False)
```

並列度は Gemini 無料枠 (60 req/min) の範囲内、v0.1 では 3 SNS 並列で余裕。

### プルダウン「指定なし」の扱い

- `options.hook == None` → hooks.md を system prompt から一切含めない (デフォ指針のみ)
- 同様に tone / emoji

→ 「何も指定しない = global.md + sns.md のデフォルト」になる。

---

## Alternatives 検討

### 案 A (採用): SNS 別 Generator + Validator + Post-processor パターン
- ✅ SNS 追加は 1 フォルダ追加で済む
- ✅ ルールが data-driven (md ファイル) + code (validator) で役割分離
- ✅ pytest でルールごとに単体テスト可能
- ⚠ クラス数増、v0.1 で小さく始めて Stage 4 で完成する

### 案 B: 単一プロンプトで全 SNS 分一気に生成
- ❌ LLM の注意力分散で品質低下 (特に Bluesky / note の特殊性を捉えきれない)
- ❌ 1 SNS だけ失敗してもトータル失敗
- → 却下

### 案 C: SNS ごとに完全独立ファイル (prompt_builder も複製)
- ❌ 共通ロジック (md ローダ / プルダウン注入) の重複
- → 却下

### 案 D: LLM Function Calling で強型出力
- ✅ JSON スキーマ違反を LLM 側で抑制
- ⚠ Gemini 2.5 Flash は Function Calling 対応済だが無料枠の制約確認必要
- → v0.2 で乗り換え検討、v0.1 は response_format=json で十分

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| LLM が文字数超過 (Threads 500 オーバー) | Threads 投稿 API 拒否 | Validator が error → UI で警告 + 編集促す。自動切り詰めはしない (意味破壊リスク) |
| LLM が JSON 出力を守らない | パース失敗 | `response_format=json_object` + パース失敗時は tenacity リトライ 2 回 + 最終的にテキスト raw で渡す |
| LLM が質問文を入れない (Threads) | Validator error | UI で警告表示、妻に「最後に問いかけを入れて」と助言文 |
| LLM が実体験を捏造 (note) | 信頼失墜 | system prompt で `[[ここを入力]]` 空欄を強制、Validator でチェック |
| プロンプト肥大化でコンテキスト溢れ | LLM が打ち切り | `prompt_builder` で組立時に文字数計測、警告ログ |
| Gemini が note の長文で出力打ち切り | 中途半端な note | `max_output_tokens` を note だけ 4096、他は 1024 |
| SNS 追加時のコード変更漏れ | 新 SNS のルール未適用 | SnsKind enum + Validator の switch を mypy strict で網羅性チェック |
| Bluesky Alt テキスト未生成 | アクセシビリティ違反 | 画像添付時は必ず `alt_texts` 生成をプロンプトで明示 + Validator で error |

---

## ロールバック手順

1. **Validator 厳しすぎで妻の投稿が止まる**: 該当ルールの severity を error → warning に下げる
2. **JSON 出力が不安定**: プロンプトをシンプル化 or response_format オプション撤去
3. **SNS 別生成が遅い**: 並列度を下げる or Gemini → Claude にフォールバック (ADR-004 参照)

---

## 計測 (成功判定)

### Stage 4 DoD

- [ ] `sns_engine/` モジュール配下の pytest:
  - 各 SNS の Validator が全ルールを網羅
  - prompt_builder がプルダウン組合せ 125 通り (5×5×5) のうち代表 10 通りでエラーなし
  - post_processor の Threads 分離 (body/reply_body) が正確
  - note のタイトル抽出 / 空欄検知
- [ ] 実 Gemini で 3 SNS 並列生成 → 全て Validator error=0
- [ ] 質問誘発文 (Threads) 100% 含まれる (10 回連続試行)
- [ ] 32 字タイトル (note) 100% 遵守

### 運用後 (v0.1 リリース 1 ヶ月)

- Validator 通過率: 95% 以上
- 妻が LLM 出力そのまま投稿した割合: 70% 以上 (編集率の逆指標)
- SNS 別 CTR 比較のために投稿履歴に `provider / model / options` 全部記録済

---

## 影響範囲

- **ADR-004 (LLM 抽象化)**: `LLMProvider` は変更なし。`sns_engine/generator.py` が `LLMProvider` を使う
- **ADR-005 (投稿履歴)**: `posts.pulldown_options` に `PulldownOptions` の JSON をそのまま格納
- **Stage 1 (Walking Skeleton)**: sns_engine は使わず直接 Gemini を叩く簡易版で OK
- **Stage 4 (プルダウン + config ローダ)** でフル実装
- **追加 SNS (v0.2 以降)**: validators/ と post_processors/ に 1 ファイル追加するだけ

---

## 実装メモ (Stage 4 実装時に参照)

```python
# src/aya_afi/sns_engine/generator.py (スケッチ)
class DefaultSnsGenerator:
    def __init__(
        self,
        llm: LLMProvider,
        prompt_builder: PromptBuilder,
        validators: Mapping[SnsKind, Validator],
        post_processors: Mapping[SnsKind, PostProcessor],
    ) -> None:
        self._llm = llm
        self._build = prompt_builder
        self._validators = validators
        self._processors = post_processors

    async def generate(
        self, product: ProductInfo, sns: SnsKind, options: PulldownOptions
    ) -> GeneratedContent:
        req = self._build.build(product, sns, options)
        resp = await self._llm.generate(req)
        raw = _parse_json(resp.text)
        content = GeneratedContent(
            sns=sns, model=resp.model, provider=resp.provider, **raw
        )
        content = self._processors[sns].process(content, product)
        content.issues = self._validators[sns].check(content)
        return content
```
