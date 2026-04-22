from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from aya_afi.affiliate.base import ProductSource
from aya_afi.affiliate.errors import (
    AffiliateAPIError,
    AffiliateConfigError,
    ProductNotFoundError,
)
from aya_afi.affiliate.rakuten import RAKUTEN_API_URL, RakutenProvider


def _mock_transport(
    status: int = 200,
    body: dict[str, Any] | None = None,
    raise_error: Exception | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if raise_error is not None:
            raise raise_error
        payload = body if body is not None else {"Items": []}
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


def test_missing_application_id_raises() -> None:
    with pytest.raises(AffiliateConfigError, match="RAKUTEN_APPLICATION_ID"):
        RakutenProvider(application_id="")


async def test_fetch_populates_product_info() -> None:
    transport = _mock_transport(
        body={
            "Items": [
                {
                    "itemName": "電気ケトル シンプル ホワイト",
                    "itemCode": "shop-abc:item-123",
                    "itemPrice": 4980,
                    "itemCaption": "蓋が外せて洗いやすい",
                    "itemUrl": "https://item.rakuten.co.jp/shop-abc/item-123/",
                    "affiliateUrl": "https://hb.afl.rakuten.co.jp/hgc/xxx",
                    "shopName": "テスト商店",
                    "mediumImageUrls": [
                        "https://thumbnail.image.rakuten.co.jp/a.jpg",
                        {"imageUrl": "https://thumbnail.image.rakuten.co.jp/b.jpg"},
                    ],
                }
            ],
            "count": 1,
        }
    )
    provider = RakutenProvider(
        application_id="test-app", affiliate_id="test-aff", transport=transport
    )
    info = await provider.fetch("https://item.rakuten.co.jp/shop-abc/item-123/")

    assert info.source == ProductSource.rakuten
    assert info.title == "電気ケトル シンプル ホワイト"
    assert info.price_yen == 4980
    assert info.affiliate_url == "https://hb.afl.rakuten.co.jp/hgc/xxx"
    assert info.shop_name == "テスト商店"
    assert info.image_urls == [
        "https://thumbnail.image.rakuten.co.jp/a.jpg",
        "https://thumbnail.image.rakuten.co.jp/b.jpg",
    ]


async def test_fetch_sends_correct_query_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        assert str(request.url).startswith(RAKUTEN_API_URL)
        return httpx.Response(
            200,
            json={
                "Items": [
                    {
                        "itemName": "x",
                        "itemCode": "s:i",
                        "itemPrice": 1,
                        "itemUrl": "https://item.rakuten.co.jp/s/i/",
                        "affiliateUrl": "https://hb.afl.rakuten.co.jp/x",
                    }
                ]
            },
        )

    provider = RakutenProvider(
        application_id="APP-ID-42",
        affiliate_id="AFF-ID-99",
        transport=httpx.MockTransport(handler),
    )
    await provider.fetch("https://item.rakuten.co.jp/shop-abc/item-123/")

    assert captured["applicationId"] == "APP-ID-42"
    assert captured["affiliateId"] == "AFF-ID-99"
    assert captured["itemCode"] == "shop-abc:item-123"
    assert captured["formatVersion"] == "2"
    assert captured["hits"] == "1"


async def test_fetch_empty_items_raises_not_found() -> None:
    provider = RakutenProvider(application_id="app", transport=_mock_transport(body={"Items": []}))
    with pytest.raises(ProductNotFoundError):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_api_error_status() -> None:
    provider = RakutenProvider(
        application_id="app",
        transport=_mock_transport(status=500, body={"error": "server"}),
    )
    with pytest.raises(AffiliateAPIError, match="500"):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_transport_error() -> None:
    provider = RakutenProvider(
        application_id="app",
        transport=_mock_transport(raise_error=httpx.ConnectError("boom")),
    )
    with pytest.raises(AffiliateAPIError, match="transport error"):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_tolerates_missing_optional_fields() -> None:
    provider = RakutenProvider(
        application_id="app",
        transport=_mock_transport(
            body={
                "Items": [
                    {
                        "itemName": "bare item",
                        "itemUrl": "https://item.rakuten.co.jp/s/i/",
                    }
                ]
            }
        ),
    )
    info = await provider.fetch("https://item.rakuten.co.jp/s/i/")
    assert info.title == "bare item"
    assert info.price_yen is None
    assert info.image_urls == []
    assert info.shop_name is None


async def test_fetch_response_not_json_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = RakutenProvider(application_id="app", transport=httpx.MockTransport(handler))
    with pytest.raises(json.JSONDecodeError):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")
