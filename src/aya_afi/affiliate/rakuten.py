"""Rakuten Ichiba Product Search API client.

Uses the public ``IchibaItem/Search`` endpoint with ``formatVersion=2`` which
returns flat item dicts (easier to deserialize than v1's ``{"Item": {...}}``
wrapping).

Docs: https://webservice.rakuten.co.jp/documentation/ichiba-item-search
"""

from __future__ import annotations

from typing import Any

import httpx

from aya_afi.affiliate.base import ProductInfo, ProductSource
from aya_afi.affiliate.errors import (
    AffiliateAPIError,
    AffiliateConfigError,
    ProductNotFoundError,
)
from aya_afi.affiliate.urls import parse_rakuten_item_code

RAKUTEN_API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"


class RakutenProvider:
    name = "rakuten"

    def __init__(
        self,
        application_id: str,
        affiliate_id: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_sec: float = 10.0,
    ) -> None:
        if not application_id:
            raise AffiliateConfigError(
                "rakuten provider requires RAKUTEN_APPLICATION_ID; "
                "get one free at https://webservice.rakuten.co.jp/"
            )
        self._application_id = application_id
        self._affiliate_id = affiliate_id
        self._transport = transport
        self._timeout_sec = timeout_sec

    async def fetch(self, url: str) -> ProductInfo:
        item_code = parse_rakuten_item_code(url)
        params: dict[str, str] = {
            "applicationId": self._application_id,
            "itemCode": item_code,
            "format": "json",
            "formatVersion": "2",
            "hits": "1",
        }
        if self._affiliate_id:
            params["affiliateId"] = self._affiliate_id

        async with httpx.AsyncClient(
            timeout=self._timeout_sec, transport=self._transport
        ) as client:
            try:
                resp = await client.get(RAKUTEN_API_URL, params=params)
            except httpx.HTTPError as e:
                raise AffiliateAPIError(f"rakuten API transport error: {e}") from e

        if resp.status_code >= 400:
            raise AffiliateAPIError(f"rakuten API returned {resp.status_code}: {resp.text[:200]}")

        body = resp.json()
        items = body.get("Items", []) if isinstance(body, dict) else []
        if not items:
            raise ProductNotFoundError(f"no rakuten item found for URL: {url}")

        item = items[0]
        return ProductInfo(
            url=url,
            source=ProductSource.rakuten,
            affiliate_url=item.get("affiliateUrl") or item.get("itemUrl") or url,
            title=str(item.get("itemName") or ""),
            price_yen=_maybe_int(item.get("itemPrice")),
            description=str(item.get("itemCaption") or ""),
            image_urls=_extract_image_urls(item.get("mediumImageUrls") or []),
            shop_name=item.get("shopName"),
            category=None,
        )


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_image_urls(raw: list[Any]) -> list[str]:
    """Handle both formatVersion=1 ({"imageUrl": "..."}) and v2 ("..." strings)."""
    urls: list[str] = []
    for img in raw:
        if isinstance(img, str):
            urls.append(img)
        elif isinstance(img, dict):
            candidate = img.get("imageUrl")
            if isinstance(candidate, str):
                urls.append(candidate)
    return urls
