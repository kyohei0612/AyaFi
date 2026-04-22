"""Rakuten Ichiba Item Search API client (2026 new portal format).

Rakuten migrated to a new Developers Portal in 2026. The API now requires:
- ``applicationId`` (UUID, not legacy 19-digit numeric)
- ``accessKey`` (``pk_...`` prefix), issued alongside applicationId
- ``Origin`` HTTP header matching one of the allowed websites registered
  with the app

Legacy ``app.rakuten.co.jp/services/api/IchibaItem/Search/20220601`` with a
numeric applicationId no longer works for newly-issued credentials.

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

RAKUTEN_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401"
DEFAULT_ORIGIN = "https://github.com"


class RakutenProvider:
    name = "rakuten"

    def __init__(
        self,
        application_id: str,
        access_key: str,
        *,
        origin: str = DEFAULT_ORIGIN,
        affiliate_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_sec: float = 10.0,
    ) -> None:
        if not application_id:
            raise AffiliateConfigError(
                "rakuten provider requires RAKUTEN_APPLICATION_ID (UUID) in .env. "
                "Get it from https://webservice.rakuten.co.jp/ → アプリ管理。"
            )
        if not access_key:
            raise AffiliateConfigError(
                "rakuten provider requires RAKUTEN_ACCESS_KEY (pk_...) in .env. "
                "Shown next to applicationId in the same dashboard (click 👁)."
            )
        if not origin:
            raise AffiliateConfigError(
                "rakuten provider requires RAKUTEN_ORIGIN matching one of the "
                "'許可されたウェブサイト' entries registered with the app."
            )
        self._application_id = application_id
        self._access_key = access_key
        self._origin = origin
        self._affiliate_id = affiliate_id
        self._transport = transport
        self._timeout_sec = timeout_sec

    async def fetch(self, url: str) -> ProductInfo:
        item_code = parse_rakuten_item_code(url)
        params: dict[str, str] = {
            "applicationId": self._application_id,
            "accessKey": self._access_key,
            "itemCode": item_code,
            "format": "json",
            "formatVersion": "2",
            "hits": "1",
        }
        if self._affiliate_id:
            params["affiliateId"] = self._affiliate_id

        # Rakuten's new API validates the Origin header against the allowed
        # website list registered with the app (NOT the HTTP Referer header,
        # despite the error message saying "REFERRER_MISSING").
        headers = {"Origin": self._origin}

        async with httpx.AsyncClient(
            timeout=self._timeout_sec, transport=self._transport
        ) as client:
            try:
                resp = await client.get(RAKUTEN_API_URL, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise AffiliateAPIError(f"rakuten API transport error: {e}") from e

        if resp.status_code >= 400:
            raise AffiliateAPIError(f"rakuten API returned {resp.status_code}: {resp.text[:200]}")

        body = resp.json()
        # New API wraps errors as {"errors": {...}} with 200 in some cases
        if isinstance(body, dict) and "errors" in body:
            err = body["errors"]
            raise AffiliateAPIError(
                f"rakuten API error {err.get('errorCode')}: {err.get('errorMessage')}"
            )
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
