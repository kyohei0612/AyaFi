from __future__ import annotations

import pytest

from aya_afi.llm.errors import LLMValidationError
from aya_afi.llm.factory import create_provider
from aya_afi.llm.mock import MockLLMProvider


def test_create_mock_provider() -> None:
    provider = create_provider("mock")
    assert isinstance(provider, MockLLMProvider)
    assert provider.name == "mock"


def test_create_gemini_without_api_key_rejected() -> None:
    with pytest.raises(LLMValidationError, match="api_key"):
        create_provider("gemini")


def test_create_gemini_with_api_key() -> None:
    # The SDK is installed and the constructor only validates the key shape.
    # Actual API calls would require a real key; health_check is not invoked here.
    provider = create_provider("gemini", api_key="sk-fake-test-key")
    assert provider.name == "gemini"


def test_create_gemini_with_fallback_key() -> None:
    provider = create_provider(
        "gemini",
        api_key="sk-primary",
        fallback_api_key="sk-secondary",
    )
    # Provider exposes 2 clients when fallback is distinct.
    assert hasattr(provider, "_clients")
    assert len(provider._clients) == 2  # type: ignore[attr-defined]


def test_create_gemini_dedupes_identical_fallback() -> None:
    # If user accidentally sets primary == fallback, we shouldn't build 2 clients.
    provider = create_provider(
        "gemini",
        api_key="sk-same",
        fallback_api_key="sk-same",
    )
    assert len(provider._clients) == 1  # type: ignore[attr-defined]


def test_create_unknown_provider_rejected() -> None:
    with pytest.raises(LLMValidationError, match="unknown"):
        create_provider("cohere")


def test_create_provider_case_sensitive() -> None:
    with pytest.raises(LLMValidationError):
        create_provider("Mock")
