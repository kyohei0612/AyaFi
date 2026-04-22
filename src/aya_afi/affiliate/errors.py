"""Affiliate-layer exception hierarchy.

Reuses ``AyaAfiError`` as base so the IPC server's ``_classify_exception``
can uniformly translate any domain error into a stable ``ErrorInfo.type``.
"""

from __future__ import annotations

from aya_afi.llm.errors import AyaAfiError


class AffiliateError(AyaAfiError):
    """Base for affiliate-layer failures."""


class UnsupportedUrlError(AffiliateError):
    """URL does not match any known product source."""


class InvalidUrlError(AffiliateError):
    """URL matched a source but failed to parse (e.g. ASIN missing)."""


class AffiliateAPIError(AffiliateError):
    """Transport or 5xx failure from an affiliate API."""


class AffiliateConfigError(AffiliateError):
    """Required credentials missing in ``.env`` (e.g. RAKUTEN_APPLICATION_ID)."""


class ProductNotFoundError(AffiliateError):
    """API returned zero items for a valid-looking URL."""
