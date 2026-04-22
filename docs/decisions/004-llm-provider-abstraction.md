# ADR-004: LLM プロバイダ抽象化

- **日付**: 2026-04-22
- **ステータス**: 承認済 (2026-04-22)
- **決定者**: kyohei
- **関連**: [ADR-001](001-initial-architecture.md), [ADR-002 Stage 1](002-mvp-scope.md)

---

## Context (問題)

- **開発時**: Claude Code (MAX プラン、テスト時は ANTHROPIC_API_KEY で直接 API)
- **v0.1 実行時**: Gemini 2.5 Flash (無料枠)
- **v0.2 以降**: Ollama ローカル LLM (妻 PC の RTX 2070)

3 プロバイダを**同じ呼び出し方**で使えないと、切替や A/B テストが不可能になる。
プロチェック rule 4「環境差異はコード分岐禁止、Settings で吸収」に従い、
**Strategy パターン + Protocol + Factory** で抽象化する。

## Decision (結論)

### Protocol 定義

```python
# src/aya_afi/llm/base.py
from typing import Protocol
from pydantic import BaseModel, Field

class GenerationRequest(BaseModel):
    schema_version: int = 1
    system_prompt: str
    user_prompt: str
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0, le=8192)
    stop_sequences: list[str] = []

class GenerationResponse(BaseModel):
    schema_version: int = 1
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str
    duration_ms: int

class LLMProvider(Protocol):
    async def generate(self, req: GenerationRequest) -> GenerationResponse: ...
    async def health_check(self) -> bool: ...
    @property
    def name(self) -> str: ...
```

### 実装ファイル (v0.1)

| ファイル | 用途 | v0.1 状態 |
|---|---|---|
| `llm/base.py` | Protocol + pydantic モデル | ✅ |
| `llm/gemini.py` | Gemini 2.5 Flash 実装 (メイン) | ✅ |
| `llm/claude.py` | Claude 実装 (開発テスト用) | ✅ |
| `llm/ollama.py` | Ollama 実装 | ⏸ v0.2 予定、スタブのみ |
| `llm/factory.py` | provider 名 → 実装解決 | ✅ |
| `llm/prompt_builder.py` | config/*.md + プルダウン → prompt | ✅ |
| `llm/errors.py` | `LLMError` 階層 | ✅ |

### ファクトリ

```python
# src/aya_afi/llm/factory.py
def create_provider(name: str, settings: LLMSettings) -> LLMProvider:
    match name:
        case "gemini": return GeminiProvider(settings.gemini)
        case "claude": return ClaudeProvider(settings.claude)
        case "ollama": return OllamaProvider(settings.ollama)
        case _: raise ValueError(f"unknown provider: {name}")
```

※ `match` は type narrowing なので OK、プロチェック 4 「環境分岐禁止」の趣旨
(異環境をコードに持ち込まない) には反しない。これは「設定による選択」。

### プロンプト組立

```python
# src/aya_afi/llm/prompt_builder.py
def build_request(
    product: ProductInfo,
    sns: SnsKind,
    options: PulldownOptions,
    config: MdConfig,
) -> GenerationRequest:
    system = "\n\n".join([
        config.global_md,        # SEO / 購買心理 / 規約
        config.sns_rules[sns],   # SNS 別ルール
    ])
    user = render_user_prompt(product, options, config)
    return GenerationRequest(system_prompt=system, user_prompt=user, ...)
```

→ LLMProvider は「組み立て済みのプロンプトを投げるだけ」の責務に純化。
プロンプト組立ロジックを LLM 非依存にして、プロバイダ切替時に壊れないようにする。

### 共通機能

- **リトライ**: `tenacity` で最大 3 回、指数バックオフ (1s, 2s, 4s)
- **レート制限**: プロバイダ別に設定 (config/app.yaml)
  - Gemini: 60 req/min (無料枠 Flash)
  - Claude: 5 req/min (デフォ、Tier による)
  - Ollama: 無制限 (ローカル)
- **LLMError 階層**:
  ```python
  class LLMError(AyaAfiError): ...
  class LLMRateLimitError(LLMError): retry_after_sec: float
  class LLMAPIError(LLMError): ...        # 5xx 等
  class LLMQuotaExceededError(LLMError): ...  # 無料枠超過
  class LLMTimeoutError(LLMError): ...
  ```

### 設定 (`config/app.yaml`)

```yaml
llm:
  provider: gemini
  gemini:
    model: gemini-2.5-flash
    temperature: 0.8
    max_output_tokens: 1024
    rate_limit_per_min: 60
  claude:
    model: claude-haiku-4-5-20251001
    temperature: 0.8
    max_output_tokens: 1024
  ollama:
    host: http://localhost:11434
    model: llama3.1-swallow:8b-instruct-q4_K_M
```

※ 各プロバイダのモデル名は `config/app.yaml` で動的に変更可能 (ハードコード禁止)。

---

## Alternatives 検討

### 案 A (採用): Protocol + Strategy + Factory
- ✅ 型が効く (Python 3.12 Protocol)
- ✅ プロバイダ追加は 1 ファイルで済む
- ✅ mock 実装で契約テスト可能
- ⚠ ファクトリが増えると煩雑 → v0.1 範囲では問題なし

### 案 B: if/else 分岐 (プロバイダ判定をコードで)
- ❌ プロチェック rule 4「環境差異はコード分岐禁止」に抵触 → 却下

### 案 C: LangChain / LlamaIndex
- ✅ 多 LLM 即対応
- ❌ 依存重い (数百 MB)、プロダクト規模にミスマッチ
- ❌ PyInstaller で凍結するのが難航
- ❌ 内部抽象が頻繁に変わる → 保守負担

### 案 D: litellm
- ✅ 100+ LLM を OpenAI 互換で叩ける
- ⚠ v0.1 範囲では自前実装の方が学習コスト低く、デバッグ楽
- ⚠ v0.2 で Ollama 追加するなら litellm の方が楽な可能性 → 将来の乗り換え検討項目

### 案 E: Callable のみの関数ベース抽象
- ✅ 最軽量
- ❌ 型表現が弱い (入出力スキーマがドキュメントでしか保証されない)
- ❌ プロチェック rule 3「全関数 type hint 必須、Any 禁止」の精神と合わない

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| Gemini 無料枠超過 (1500 req/日) | 文章生成不可 | `LLMQuotaExceededError` を UI に明示表示 + 次回リセット時刻 |
| Gemini レート超過 (60 req/min) | 連続投稿で失敗 | tenacity でバックオフ再試行 + UI に進行状況 |
| Claude API 料金超過 (ANTHROPIC_API_KEY の従量) | 請求額が跳ねる | 開発テスト用なので本番 config から除外。UI に warning 表示 |
| Ollama 未起動 (v0.2 以降) | 切替時にエラー | health_check で事前検知、起動ガイドを UI 表示 |
| config/app.yaml のプロバイダ名が typo | 起動失敗 | `create_provider` で即例外 + 有効値列挙 |
| プロンプト組立の文字数超過 | トークン制限エラー | `build_request` 内で max_context チェック、警告ログ |
| 異プロバイダ間の temperature 意味差異 | 出力品質バラつき | 各プロバイダでクリッピング (例: Gemini は 0-2、Claude は 0-1)、ログに記録 |

---

## ロールバック手順

1. **Gemini が落ちた**: `config/app.yaml` の `provider: gemini` → `provider: claude` に書き換え再起動
2. **全 LLM プロバイダが死んだ**: 「手動コピペモード」UI に切替 — プロンプトを表示し、
   妻が外部 LLM (ブラウザ版 Gemini/ChatGPT/Claude) にコピペして戻す運用
3. **抽象化自体が負債になった**: litellm に乗り換え (Protocol は維持、内部を置換)

---

## 計測 (成功判定)

- [ ] Stage 1 完了時、Gemini で 1 プロンプト → テキスト返却の smoke pass
- [ ] `test_llm_contract.py`: MockProvider を作り、Protocol 契約を全実装が満たすことを検証
- [ ] `test_factory.py`: 全プロバイダ名が正しく解決される / typo で例外
- [ ] `test_prompt_builder.py`: 同じ入力 → 同じ出力 (決定的)
- [ ] レート制限テスト: 61 req/min で tenacity リトライが発動
- [ ] プロバイダ切替: config 書き換え + 再起動で実プロバイダが変わる

---

## 実装メモ (Stage 1 実装時に参照)

```python
# src/aya_afi/llm/gemini.py (スケッチ)
class GeminiProvider:
    name = "gemini"
    def __init__(self, settings: GeminiSettings):
        self._client = genai.Client(api_key=settings.api_key)
        self._model = settings.model
        self._limiter = AsyncLimiter(settings.rate_limit_per_min, 60)

    async def generate(self, req: GenerationRequest) -> GenerationResponse:
        async with self._limiter:
            t0 = time.time()
            try:
                resp = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=req.user_prompt,
                    config={"system_instruction": req.system_prompt,
                            "temperature": req.temperature,
                            "max_output_tokens": req.max_output_tokens},
                )
            except ResourceExhausted as e:
                raise LLMQuotaExceededError(str(e)) from e
            return GenerationResponse(
                text=resp.text, tokens_in=resp.usage.prompt_tokens,
                tokens_out=resp.usage.candidates_tokens, model=self._model,
                provider=self.name, duration_ms=int((time.time() - t0) * 1000),
            )

    async def health_check(self) -> bool:
        try: await self._client.aio.models.list(); return True
        except Exception: return False
```
