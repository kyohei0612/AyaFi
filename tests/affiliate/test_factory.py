from __future__ import annotations

import pytest

from aya_afi.affiliate.errors import AffiliateConfigError, UnsupportedUrlError
from aya_afi.affiliate.factory import create_provider_for_url
from aya_afi.affiliate.mock import MockAffiliateProvider
from aya_afi.affiliate.moshimo import MoshimoAmazonProvider
from aya_afi.affiliate.rakuten import RakutenProvider
from aya_afi.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "llm_provider": "mock",
        "affiliate_force_mock": False,
        "moshimo_a_id": None,
        "moshimo_amazon_p_id": None,
        "moshimo_amazon_pc_id": None,
        "moshimo_amazon_pl_id": None,
        "rakuten_application_id": None,
        "rakuten_affiliate_id": None,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_force_mock_short_circuits_all_routing() -> None:
    settings = _settings(affiliate_force_mock=True)
    provider = create_provider_for_url("https://item.rakuten.co.jp/a/b/", settings)
    assert isinstance(provider, MockAffiliateProvider)


def test_amazon_url_routes_to_moshimo_with_all_ids() -> None:
    settings = _settings(
        moshimo_a_id="A",
        moshimo_amazon_p_id="P",
        moshimo_amazon_pc_id="PC",
        moshimo_amazon_pl_id="PL",
    )
    provider = create_provider_for_url("https://amazon.co.jp/dp/B0TEST", settings)
    assert isinstance(provider, MoshimoAmazonProvider)


def test_amazon_url_without_moshimo_ids_raises_config_error() -> None:
    settings = _settings()  # no moshimo ids
    with pytest.raises(AffiliateConfigError):
        create_provider_for_url("https://amazon.co.jp/dp/B0TEST", settings)


def test_rakuten_url_routes_to_rakuten() -> None:
    settings = _settings(rakuten_application_id="APP")
    provider = create_provider_for_url("https://item.rakuten.co.jp/shop/item/", settings)
    assert isinstance(provider, RakutenProvider)


def test_rakuten_url_without_app_id_raises_config_error() -> None:
    settings = _settings()
    with pytest.raises(AffiliateConfigError, match="RAKUTEN_APPLICATION_ID"):
        create_provider_for_url("https://item.rakuten.co.jp/shop/item/", settings)


def test_unknown_host_rejected() -> None:
    settings = _settings()
    with pytest.raises(UnsupportedUrlError):
        create_provider_for_url("https://yahoo.co.jp/shopping/x", settings)
