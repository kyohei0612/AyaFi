"""URL classification + parsing for supported product sources."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from aya_afi.affiliate.base import ProductSource
from aya_afi.affiliate.errors import InvalidUrlError, UnsupportedUrlError

_AMAZON_FULL_HOSTS = ("amazon.co.jp",)
_AMAZON_SHORT_HOSTS = ("amzn.to", "amzn.asia")
_RAKUTEN_HOSTS = ("item.rakuten.co.jp",)

# Matches ASIN-shaped suffix after /dp/, /gp/product/, /gp/aw/d/.
_ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:[/?]|$)")


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def classify_url(url: str) -> ProductSource:
    """Return the ``ProductSource`` a URL belongs to (``unknown`` if no match)."""
    host = _host(url)
    if any(host == h or host.endswith("." + h) for h in _AMAZON_FULL_HOSTS):
        return ProductSource.amazon
    if any(host == h or host.endswith("." + h) for h in _RAKUTEN_HOSTS):
        return ProductSource.rakuten
    return ProductSource.unknown


def assert_full_url(url: str) -> None:
    """Reject Amazon short URLs (``amzn.to`` / ``amzn.asia``) with a helpful message.

    These require a network HEAD request to resolve, which is out of scope for
    Stage 2. The wife should paste the canonical amazon.co.jp URL.
    """
    host = _host(url)
    if any(host == h or host.endswith("." + h) for h in _AMAZON_SHORT_HOSTS):
        raise UnsupportedUrlError(
            "Amazon 短縮 URL (amzn.to / amzn.asia) は未対応です。"
            "完全 URL (amazon.co.jp/dp/...) をコピーし直してください。"
        )


def parse_amazon_asin(url: str) -> str:
    """Extract the 10-character ASIN from an amazon.co.jp product URL."""
    assert_full_url(url)
    match = _ASIN_RE.search(urlparse(url).path)
    if not match:
        raise InvalidUrlError(f"ASIN not found in URL: {url}")
    return match.group(1)


def parse_rakuten_item_code(url: str) -> str:
    """Extract ``shop-code:item-code`` from a Rakuten Ichiba product URL.

    Rakuten URL shape: ``https://item.rakuten.co.jp/{shop}/{item}/?q=...``.
    """
    path = urlparse(url).path.strip("/")
    parts = path.split("/") if path else []
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise InvalidUrlError(f"cannot extract itemCode from rakuten URL: {url}")
    return f"{parts[0]}:{parts[1]}"
