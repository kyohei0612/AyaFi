from __future__ import annotations

from aya_afi.affiliate.base import ProductInfo, ProductSource
from aya_afi.affiliate.mock import MockAffiliateProvider


async def test_default_returns_canned_fields() -> None:
    provider = MockAffiliateProvider()
    info = await provider.fetch("https://example.com/foo")
    assert info.url == "https://example.com/foo"
    assert info.price_yen == 1980
    assert info.title.startswith("[MOCK PRODUCT]")


async def test_canned_override_returned_verbatim() -> None:
    canned = ProductInfo(
        url="https://x",
        source=ProductSource.rakuten,
        affiliate_url="https://aff/x",
        title="preset",
    )
    provider = MockAffiliateProvider(canned=canned)
    info = await provider.fetch("https://different.url/")
    assert info is canned
