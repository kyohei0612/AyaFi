"""Affiliate provider Protocol + pydantic data classes.

``AffiliateProvider`` is the single interface the rest of the app depends on.
Concrete providers (``RakutenProvider``, ``MoshimoAmazonProvider``,
``MockAffiliateProvider``) live in sibling modules.

See: docs/decisions/002-mvp-scope.md (F01-F02).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class ProductSource(StrEnum):
    amazon = "amazon"
    rakuten = "rakuten"
    unknown = "unknown"


class ProductInfo(BaseModel):
    """Best-effort snapshot of a product.

    Rakuten Web Service populates most fields. Amazon (via もしも) typically
    only has ``url`` / ``source`` / ``affiliate_url`` because we deliberately
    don't scrape or call PA-API (ADR-002); the user fills title/description.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    url: str = Field(..., description="Original URL the user provided.")
    source: ProductSource
    affiliate_url: str = Field(
        ...,
        description="Clickable affiliate URL the user pastes into the SNS post.",
    )
    title: str = Field(default="", description="Product title; may be empty.")
    price_yen: int | None = Field(default=None, ge=0)
    description: str = ""
    image_urls: list[str] = Field(default_factory=list)
    shop_name: str | None = None
    category: str | None = None


@runtime_checkable
class AffiliateProvider(Protocol):
    """Implemented by every concrete affiliate-link provider."""

    name: str

    async def fetch(self, url: str) -> ProductInfo: ...
