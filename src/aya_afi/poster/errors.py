"""Poster-layer exception hierarchy.

Reuses ``AyaAfiError`` base so IPC server's ``_classify_exception`` can map
uniformly.
"""

from __future__ import annotations

from aya_afi.llm.errors import AyaAfiError


class PosterError(AyaAfiError):
    """Base for posting failures."""


class PosterAuthError(PosterError):
    """Auth token invalid / revoked (permanent, not retryable)."""


class PosterRateLimitError(PosterError):
    """Provider-enforced rate limit; retry after ``retry_after_sec``."""

    def __init__(self, message: str, retry_after_sec: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_sec = retry_after_sec


class PosterAPIError(PosterError):
    """Transport / 5xx failure (retryable)."""


class PosterValidationError(PosterError):
    """Provider rejected the content (char limit / policy / media type)."""


class PosterConfigError(PosterError):
    """Required credentials missing in ``.env`` (e.g. THREADS_ACCESS_TOKEN)."""
