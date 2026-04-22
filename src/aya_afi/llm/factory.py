"""Factory for selecting an ``LLMProvider`` from a string provider name.

Only way to construct concrete providers in application code. Tests should
instantiate ``MockLLMProvider`` directly instead of going through the factory.
"""

from __future__ import annotations

from aya_afi.llm.base import LLMProvider
from aya_afi.llm.errors import LLMValidationError
from aya_afi.llm.gemini import GeminiProvider
from aya_afi.llm.mock import MockLLMProvider


def create_provider(
    name: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    fallback_api_key: str | None = None,
) -> LLMProvider:
    """Return a configured ``LLMProvider`` for the given name.

    :param fallback_api_key: For ``gemini`` only. Secondary key used when the
        primary hits transient 5xx / rate-limit errors.
    :raises LLMValidationError: if ``name`` is unknown or required settings
        (e.g. ``api_key`` for ``gemini``) are missing.
    """
    match name:
        case "mock":
            return MockLLMProvider()
        case "gemini":
            if not api_key:
                raise LLMValidationError(
                    "gemini provider requires api_key; set GEMINI_API_KEY in .env"
                )
            return GeminiProvider(
                api_key=api_key,
                model=model or "gemini-2.5-flash",
                fallback_api_key=fallback_api_key,
            )
        case _:
            raise LLMValidationError(f"unknown LLM provider '{name}'. Known: mock, gemini.")
