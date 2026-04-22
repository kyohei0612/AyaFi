"""Gemini 2.5 Flash provider (Google AI Studio free tier).

Imports the ``google-genai`` SDK lazily so the module can be loaded even when
the SDK is not installed; the import happens in ``__init__`` only when the
provider is actually constructed.

Transient failures (503 UNAVAILABLE, rate limits) are retried automatically
via tenacity. Quota exhaustion and validation errors are NOT retried.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from aya_afi.llm.base import GenerationRequest, GenerationResponse
from aya_afi.llm.errors import (
    LLMAPIError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMValidationError,
)

if TYPE_CHECKING:
    from google.genai import Client

DEFAULT_MODEL = "gemini-2.5-flash"

_log = logging.getLogger("aya_afi.llm.gemini")
_RETRYABLE = (LLMAPIError, LLMRateLimitError)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        fallback_api_key: str | None = None,
    ) -> None:
        if not api_key:
            raise LLMValidationError("gemini api_key is required")
        try:
            # Lazy import: allows the module to load without the optional SDK.
            from google import genai
        except ImportError as e:  # pragma: no cover - environment-dependent
            raise LLMAPIError(
                "google-genai SDK not installed. "
                "Run `uv pip install -e '.[llm]'` or `pip install google-genai`."
            ) from e
        self._model = model
        self._clients: list[Client] = [genai.Client(api_key=api_key)]
        # Dedup: skip fallback if it's identical to primary (user accidentally
        # set both to the same value).
        if fallback_api_key and fallback_api_key != api_key:
            self._clients.append(genai.Client(api_key=fallback_api_key))

    async def generate(self, req: GenerationRequest) -> GenerationResponse:
        config: dict[str, Any] = {
            "system_instruction": req.system_prompt,
            "temperature": req.temperature,
            "max_output_tokens": req.max_output_tokens,
            # Gemini 2.5 Flash enables Dynamic Thinking by default, which consumes
            # tokens from max_output_tokens before any visible text is produced.
            # For SNS-length prose we don't need reasoning - disable to maximize
            # visible output and latency. If a future caller needs thinking,
            # we can thread a ``thinking_budget`` knob through GenerationRequest.
            "thinking_config": {"thinking_budget": 0},
        }
        if req.stop_sequences:
            config["stop_sequences"] = req.stop_sequences
        if req.response_format == "json":
            config["response_mime_type"] = "application/json"

        # Outer loop: try each configured API key in order.
        # Inner loop (tenacity): retry transient failures with the same key.
        # Non-retryable errors (validation / quota exhausted) propagate immediately.
        errors: list[str] = []
        for idx, client in enumerate(self._clients):
            try:
                return await self._retry_generate(client, req, config)
            except _RETRYABLE as e:
                errors.append(f"key[{idx}]: {str(e)[:150]}")
                _log.warning(
                    "gemini_key_exhausted",
                    extra={
                        "event": "gemini_key_exhausted",
                        "key_index": idx,
                        "will_try_next": idx + 1 < len(self._clients),
                    },
                )
        raise LLMAPIError(f"all {len(self._clients)} gemini key(s) failed: " + " | ".join(errors))

    async def _retry_generate(
        self,
        client: Client,
        req: GenerationRequest,
        config: dict[str, Any],
    ) -> GenerationResponse:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.5, min=2, max=12),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
            before_sleep=before_sleep_log(_log, logging.WARNING),
        ):
            with attempt:
                return await self._generate_once(client, req, config)
        # Unreachable - AsyncRetrying with reraise=True always returns or raises.
        raise LLMAPIError("gemini retry loop exhausted without result")

    async def _generate_once(
        self,
        client: Client,
        req: GenerationRequest,
        config: dict[str, Any],
    ) -> GenerationResponse:
        start = time.monotonic()
        try:
            resp = await client.aio.models.generate_content(
                model=self._model,
                contents=req.user_prompt,
                config=config,  # type: ignore[arg-type]  # SDK accepts dicts at runtime
            )
        except Exception as e:  # translate SDK errors to LLM* hierarchy
            raise _translate_error(e) from e
        duration = int((time.monotonic() - start) * 1000)

        usage = getattr(resp, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)

        return GenerationResponse(
            text=resp.text or "",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=self._model,
            provider=self.name,
            duration_ms=duration,
        )

    async def health_check(self) -> bool:
        # At least one configured key must be usable.
        for idx, client in enumerate(self._clients):
            try:
                async for _ in await client.aio.models.list():
                    break
                return True
            except Exception as e:  # pragma: no cover - network-dependent
                _log.warning(
                    "gemini_health_check_failed",
                    extra={
                        "event": "gemini_health_check_failed",
                        "key_index": idx,
                        "error": str(e)[:200],
                    },
                )
        return False


def _translate_error(e: BaseException) -> Exception:
    """Best-effort mapping from google-genai exceptions to ``LLMError`` types."""
    message = str(e)
    lowered = message.lower()
    if "resource_exhausted" in lowered or "quota" in lowered:
        return LLMQuotaExceededError(message)
    if "rate" in lowered and "limit" in lowered:
        return LLMRateLimitError(message)
    if "invalid" in lowered or "malformed" in lowered:
        return LLMValidationError(message)
    return LLMAPIError(message)
