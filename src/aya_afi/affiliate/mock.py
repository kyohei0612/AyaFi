"""Mock affiliate provider for tests and keyless dev runs."""

from __future__ import annotations

from aya_afi.affiliate.base import ProductInfo, ProductSource


class MockAffiliateProvider:
    name = "mock"

    def __init__(self, canned: ProductInfo | None = None) -> None:
        self._canned = canned

    async def fetch(self, url: str) -> ProductInfo:
        if self._canned is not None:
            return self._canned
        return ProductInfo(
            url=url,
            source=ProductSource.unknown,
            affiliate_url=url,
            title="[MOCK PRODUCT] Sample Item",
            price_yen=1980,
            description="Mock description used for keyless dev and tests.",
        )
