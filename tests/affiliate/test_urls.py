from __future__ import annotations

import pytest

from aya_afi.affiliate.base import ProductSource
from aya_afi.affiliate.errors import InvalidUrlError, UnsupportedUrlError
from aya_afi.affiliate.urls import (
    classify_url,
    parse_amazon_asin,
    parse_rakuten_item_code,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.amazon.co.jp/dp/B08L5WRWGL", ProductSource.amazon),
        ("https://amazon.co.jp/dp/B08L5WRWGL/ref=abc", ProductSource.amazon),
        ("https://item.rakuten.co.jp/shop/item/", ProductSource.rakuten),
        ("https://item.rakuten.co.jp/shop/item/?v=1", ProductSource.rakuten),
        ("https://example.com/foo", ProductSource.unknown),
        ("https://www.yahoo.co.jp", ProductSource.unknown),
    ],
)
def test_classify_url(url: str, expected: ProductSource) -> None:
    assert classify_url(url) == expected


def test_amazon_short_url_rejected_with_helpful_message() -> None:
    with pytest.raises(UnsupportedUrlError, match="短縮 URL"):
        parse_amazon_asin("https://amzn.to/abcdef")


def test_parse_amazon_asin_dp() -> None:
    assert parse_amazon_asin("https://amazon.co.jp/dp/B08L5WRWGL") == "B08L5WRWGL"


def test_parse_amazon_asin_gp_product() -> None:
    assert parse_amazon_asin("https://amazon.co.jp/gp/product/B08L5WRWGL/") == "B08L5WRWGL"


def test_parse_amazon_asin_with_query_and_ref() -> None:
    assert (
        parse_amazon_asin("https://www.amazon.co.jp/dp/B08L5WRWGL/ref=cm_sw_su?th=1")
        == "B08L5WRWGL"
    )


def test_parse_amazon_asin_with_japanese_slug() -> None:
    url = "https://www.amazon.co.jp/%E5%95%86%E5%93%81/dp/B08L5WRWGL/ref=xx"
    assert parse_amazon_asin(url) == "B08L5WRWGL"


def test_parse_amazon_asin_missing_raises() -> None:
    with pytest.raises(InvalidUrlError):
        parse_amazon_asin("https://amazon.co.jp/s?k=search")


def test_parse_rakuten_item_code_basic() -> None:
    assert (
        parse_rakuten_item_code("https://item.rakuten.co.jp/shop-abc/item-123/")
        == "shop-abc:item-123"
    )


def test_parse_rakuten_item_code_with_query() -> None:
    assert (
        parse_rakuten_item_code("https://item.rakuten.co.jp/shop-abc/item-123/?scid=x")
        == "shop-abc:item-123"
    )


def test_parse_rakuten_item_code_missing_parts() -> None:
    with pytest.raises(InvalidUrlError):
        parse_rakuten_item_code("https://item.rakuten.co.jp/")


def test_parse_rakuten_item_code_only_shop() -> None:
    with pytest.raises(InvalidUrlError):
        parse_rakuten_item_code("https://item.rakuten.co.jp/shop/")
