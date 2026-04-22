"""LLM error hierarchy.

All exceptions that escape an ``LLMProvider.generate`` implementation MUST be
instances of ``LLMError``. Raw SDK exceptions should be translated at the
provider boundary so callers have a stable set of types to switch on.
"""

from __future__ import annotations


class AyaAfiError(Exception):
    """Base class for all aya-afi domain errors."""


class LLMError(AyaAfiError):
    """Base class for LLM-related failures."""


class LLMAPIError(LLMError):
    """Transport or provider-side 5xx / unknown failure."""


class LLMRateLimitError(LLMError):
    """Provider-enforced rate limit hit. ``retry_after_sec`` is advisory."""

    def __init__(self, message: str, retry_after_sec: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_sec = retry_after_sec


class LLMQuotaExceededError(LLMError):
    """Free-tier or billing quota exhausted (distinct from transient rate limit)."""


class LLMTimeoutError(LLMError):
    """Provider took longer than the request's configured timeout."""


class LLMValidationError(LLMError):
    """Provider rejected the request as malformed or policy-violating."""
