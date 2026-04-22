from __future__ import annotations

import pytest
from pydantic import ValidationError

from aya_afi.llm.base import (
    SCHEMA_VERSION,
    GenerationRequest,
    GenerationResponse,
    LLMProvider,
)
from aya_afi.llm.mock import MockLLMProvider


def test_generation_request_defaults() -> None:
    req = GenerationRequest(system_prompt="s", user_prompt="u")
    assert req.temperature == 0.8
    assert req.max_output_tokens == 1024
    assert req.response_format == "text"
    assert req.schema_version == SCHEMA_VERSION


def test_generation_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate({"system_prompt": "s", "user_prompt": "u", "foo": "bar"})


def test_generation_request_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(system_prompt="s", user_prompt="u", temperature=-0.1)
    with pytest.raises(ValidationError):
        GenerationRequest(system_prompt="s", user_prompt="u", temperature=2.1)


def test_generation_request_max_tokens_bounds() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(system_prompt="s", user_prompt="u", max_output_tokens=0)
    with pytest.raises(ValidationError):
        GenerationRequest(system_prompt="s", user_prompt="u", max_output_tokens=10_000)


def test_generation_response_requires_positive_counts() -> None:
    with pytest.raises(ValidationError):
        GenerationResponse(
            text="x",
            tokens_in=-1,
            tokens_out=0,
            model="m",
            provider="p",
            duration_ms=0,
        )


def test_mock_satisfies_protocol() -> None:
    # runtime_checkable Protocol: isinstance works structurally.
    provider = MockLLMProvider()
    assert isinstance(provider, LLMProvider)
    assert provider.name == "mock"
