"""Route a product URL to the configured ``AffiliateProvider``.

The only place in the app that decides which concrete provider to instantiate
for a given URL. Callers depend on the ``AffiliateProvider`` Protocol only.
"""

from __future__ import annotations

from aya_afi.affiliate.base import AffiliateProvider, ProductSource
from aya_afi.affiliate.errors import AffiliateConfigError, UnsupportedUrlError
from aya_afi.affiliate.mock import MockAffiliateProvider
from aya_afi.affiliate.moshimo import MoshimoAmazonProvider
from aya_afi.affiliate.rakuten import RakutenProvider
from aya_afi.affiliate.urls import classify_url
from aya_afi.config.settings import Settings


def create_provider_for_url(url: str, settings: Settings) -> AffiliateProvider:
    """Return a configured provider for ``url`` based on ``settings``.

    :raises UnsupportedUrlError: if the URL is not Amazon or Rakuten (or a
        known short-URL form we intentionally reject).
    :raises AffiliateConfigError: if the matching provider's credentials
        are missing from ``.env``.
    """
    if settings.affiliate_force_mock:
        return MockAffiliateProvider()

    source = classify_url(url)
    match source:
        case ProductSource.amazon:
            return MoshimoAmazonProvider(
                a_id=settings.moshimo_a_id or "",
                p_id=settings.moshimo_amazon_p_id or "",
                pc_id=settings.moshimo_amazon_pc_id or "",
                pl_id=settings.moshimo_amazon_pl_id or "",
            )
        case ProductSource.rakuten:
            if not settings.rakuten_application_id:
                raise AffiliateConfigError(
                    "RAKUTEN_APPLICATION_ID (UUID) is required in .env to fetch "
                    "Rakuten product info; get it free at "
                    "https://webservice.rakuten.co.jp/"
                )
            if not settings.rakuten_access_key:
                raise AffiliateConfigError(
                    "RAKUTEN_ACCESS_KEY (pk_...) is required in .env for the "
                    "new Rakuten API. Copy it from the dashboard next to the "
                    "applicationId (click the 👁 icon to reveal)."
                )
            return RakutenProvider(
                application_id=settings.rakuten_application_id,
                access_key=settings.rakuten_access_key,
                origin=settings.rakuten_origin,
                affiliate_id=settings.rakuten_affiliate_id,
            )
        case ProductSource.unknown:
            raise UnsupportedUrlError(
                f"URL is neither amazon.co.jp nor item.rakuten.co.jp: {url}. "
                "Paste a full product URL from a supported site."
            )
