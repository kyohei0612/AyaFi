from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from aya_afi.affiliate.base import ProductSource
from aya_afi.affiliate.errors import AffiliateConfigError
from aya_afi.affiliate.moshimo import MoshimoAmazonProvider


def _provider() -> MoshimoAmazonProvider:
    return MoshimoAmazonProvider(a_id="A1", p_id="P1", pc_id="PC1", pl_id="PL1")


def test_missing_a_id_rejected() -> None:
    with pytest.raises(AffiliateConfigError, match="MOSHIMO_A_ID"):
        MoshimoAmazonProvider(a_id="", p_id="x", pc_id="y", pl_id="z")


def test_missing_promotion_ids_rejected_lists_all() -> None:
    with pytest.raises(AffiliateConfigError, match="MOSHIMO_AMAZON_P_ID"):
        MoshimoAmazonProvider(a_id="A", p_id="", pc_id="", pl_id="")


def test_build_click_url_has_all_parameters() -> None:
    url = _provider().build_click_url("https://www.amazon.co.jp/dp/B00TEST123")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "af.moshimo.com"
    assert parsed.path == "/af/c/click"
    assert params["a_id"] == ["A1"]
    assert params["p_id"] == ["P1"]
    assert params["pc_id"] == ["PC1"]
    assert params["pl_id"] == ["PL1"]
    assert params["url"] == ["https://www.amazon.co.jp/dp/B00TEST123"]


async def test_fetch_returns_canonical_url_and_affiliate() -> None:
    provider = _provider()
    info = await provider.fetch("https://www.amazon.co.jp/%E5%95%86%E5%93%81/dp/B00TEST123/ref=xx")
    assert info.source == ProductSource.amazon
    assert info.url.startswith("https://www.amazon.co.jp")
    assert "af.moshimo.com/af/c/click" in info.affiliate_url
    assert "B00TEST123" in info.affiliate_url
    # Product info fields are empty (user fills per ADR-002).
    assert info.title == ""
    assert info.description == ""
    assert info.image_urls == []
