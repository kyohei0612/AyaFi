from __future__ import annotations

from aya_afi.llm.base import GenerationRequest
from aya_afi.llm.mock import MockLLMProvider


async def test_canned_response_returned_verbatim() -> None:
    provider = MockLLMProvider(canned_response="fixed reply")
    resp = await provider.generate(GenerationRequest(system_prompt="s", user_prompt="u"))
    assert resp.text == "fixed reply"
    assert resp.provider == "mock"
    assert resp.model == "mock-deterministic-v1"


async def test_default_reply_is_deterministic() -> None:
    provider = MockLLMProvider()
    req = GenerationRequest(
        system_prompt="system instruction",
        user_prompt="user message",
        temperature=0.5,
    )
    first = await provider.generate(req)
    second = await provider.generate(req)
    assert first.text == second.text


async def test_tokens_are_populated() -> None:
    provider = MockLLMProvider()
    resp = await provider.generate(
        GenerationRequest(system_prompt="hello world", user_prompt="another prompt")
    )
    assert resp.tokens_in > 0
    assert resp.tokens_out > 0


async def test_health_check_always_ok() -> None:
    provider = MockLLMProvider()
    assert await provider.health_check() is True
