"""Deterministic mock LLM provider.

Used in two places:
- unit tests (contract testing against ``LLMProvider``)
- ``provider: mock`` mode for keyless dev runs (e.g. CI, demos without API quota)

The response is a deterministic function of the request, so snapshot tests
are stable across CI runs.
"""

from __future__ import annotations

import asyncio
import time

from aya_afi.llm.base import GenerationRequest, GenerationResponse


class MockLLMProvider:
    name = "mock"

    def __init__(
        self,
        canned_response: str | None = None,
        delay_ms: int = 0,
    ) -> None:
        self._canned = canned_response
        self._delay_ms = delay_ms

    async def generate(self, req: GenerationRequest) -> GenerationResponse:
        if self._delay_ms > 0:
            await asyncio.sleep(self._delay_ms / 1000)
        start = time.monotonic()
        text = self._canned if self._canned is not None else _default_reply(req)
        duration = int((time.monotonic() - start) * 1000)
        return GenerationResponse(
            text=text,
            tokens_in=_rough_token_count(req.system_prompt + req.user_prompt),
            tokens_out=_rough_token_count(text),
            model="mock-deterministic-v1",
            provider=self.name,
            duration_ms=duration,
        )

    async def health_check(self) -> bool:
        return True


def _default_reply(req: GenerationRequest) -> str:
    return (
        "[MOCK LLM RESPONSE]\n"
        f"system[:80]={req.system_prompt[:80]}\n"
        f"user[:80]={req.user_prompt[:80]}\n"
        f"temperature={req.temperature} format={req.response_format}"
    )


def _rough_token_count(text: str) -> int:
    """Approximate token count (~4 chars per token). Deterministic."""
    return max(1, len(text) // 4)
