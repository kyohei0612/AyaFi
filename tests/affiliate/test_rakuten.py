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


def _provider(**overrides: Any) -> RakutenProvider:
    defaults: dict[str, Any] = {
        "application_id": "uuid-test-app",
        "access_key": "pk_test_access_key",
    }
    defaults.update(overrides)
    return RakutenProvider(**defaults)


def test_missing_application_id_raises() -> None:
    with pytest.raises(AffiliateConfigError, match="RAKUTEN_APPLICATION_ID"):
        RakutenProvider(application_id="", access_key="pk_x")


def test_missing_access_key_raises() -> None:
    with pytest.raises(AffiliateConfigError, match="RAKUTEN_ACCESS_KEY"):
        RakutenProvider(application_id="uuid-x", access_key="")


def test_missing_origin_raises() -> None:
    with pytest.raises(AffiliateConfigError, match="RAKUTEN_ORIGIN"):
        RakutenProvider(application_id="uuid", access_key="pk", origin="")


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
    provider = _provider(affiliate_id="test-aff", transport=transport)
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


async def test_fetch_sends_correct_query_params_and_origin_header() -> None:
    captured_params: dict[str, str] = {}
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        captured_headers.update(dict(request.headers))
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

    provider = _provider(
        application_id="APP-ID-42",
        access_key="pk_real_key",
        origin="https://github.com/foo/bar",
        affiliate_id="AFF-ID-99",
        transport=httpx.MockTransport(handler),
    )
    await provider.fetch("https://item.rakuten.co.jp/shop-abc/item-123/")

    assert captured_params["applicationId"] == "APP-ID-42"
    assert captured_params["accessKey"] == "pk_real_key"
    assert captured_params["affiliateId"] == "AFF-ID-99"
    assert captured_params["itemCode"] == "shop-abc:item-123"
    assert captured_params["formatVersion"] == "2"
    assert captured_params["hits"] == "1"
    # Origin header is what Rakuten's new API actually validates (despite the
    # error message saying "REFERRER_MISSING").
    assert captured_headers["origin"] == "https://github.com/foo/bar"


async def test_fetch_empty_items_raises_not_found() -> None:
    provider = _provider(transport=_mock_transport(body={"Items": []}))
    with pytest.raises(ProductNotFoundError):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_api_error_status() -> None:
    provider = _provider(
        transport=_mock_transport(status=500, body={"error": "server"}),
    )
    with pytest.raises(AffiliateAPIError, match="500"):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_api_error_body_with_200_status() -> None:
    """New Rakuten API sometimes returns 200 with ``{"errors": {...}}`` body."""
    provider = _provider(
        transport=_mock_transport(
            body={
                "errors": {
                    "errorCode": 403,
                    "errorMessage": "REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING",
                }
            }
        ),
    )
    with pytest.raises(AffiliateAPIError, match="REFERRER_MISSING"):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_transport_error() -> None:
    provider = _provider(
        transport=_mock_transport(raise_error=httpx.ConnectError("boom")),
    )
    with pytest.raises(AffiliateAPIError, match="transport error"):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")


async def test_fetch_tolerates_missing_optional_fields() -> None:
    provider = _provider(
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

    provider = _provider(transport=httpx.MockTransport(handler))
    with pytest.raises(json.JSONDecodeError):
        await provider.fetch("https://item.rakuten.co.jp/s/i/")
