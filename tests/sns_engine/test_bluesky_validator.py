from __future__ import annotations

import pytest

from aya_afi.sns_engine.base import PostMode, SnsKind, ValidationSeverity
from aya_afi.sns_engine.validators.bluesky import (
    BLUESKY_MAX_CHARS,
    validate_bluesky_post,
)


def _rule_ids(report, severity: ValidationSeverity | None = None) -> list[str]:
    issues = report.issues
    if severity is not None:
        issues = [i for i in issues if i.severity == severity]
    return [i.rule_id for i in issues]


def test_valid_affiliate_post_passes() -> None:
    body = (
        "忙しい朝のコーヒータイムに投入。600ml 1 分半で沸くのが主婦視点でも嬉しい。\n"
        "蓋が外せて洗いやすい点も地味に大事。\n"
        "https://item.rakuten.co.jp/shop/abc/\n"
        "#時短家事 #PR"
    )
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert report.sns == SnsKind.bluesky
    assert report.mode == PostMode.affiliate
    assert not report.has_errors


def test_valid_preparation_post_passes() -> None:
    body = (
        "寝かしつけで一緒に寝落ちしたら 18 時でした。\n"
        "家族に笑われつつ、たまには休むのも悪くないなと。\n"
        "#日々のこと #子育て"
    )
    report = validate_bluesky_post(body, PostMode.preparation)
    assert not report.has_errors
    # Informational suggestions only (if any)


def test_over_300_chars_error() -> None:
    body = "あ" * 301 + " #日々のこと"
    report = validate_bluesky_post(body, PostMode.preparation)
    assert "bluesky.too_long" in _rule_ids(report, ValidationSeverity.error)


def test_no_hashtags_warning() -> None:
    body = "今日は寒い。1200w 電気ケトルが神。"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.no_hashtags" in _rule_ids(report, ValidationSeverity.warning)


def test_six_hashtags_warning() -> None:
    body = "今日の 1 品 1500 円。\n#時短 #家事 #子育て #QOL #買い物 #PR"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.too_many_hashtags" in _rule_ids(report, ValidationSeverity.warning)


def test_affiliate_missing_pr_tag_error() -> None:
    body = "便利な時計買った。80g で軽い。みんなのおすすめは?\n#時短家事"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.missing_pr_tag" in _rule_ids(report, ValidationSeverity.error)


def test_preparation_with_pr_tag_warning() -> None:
    body = "失敗談の話です、みんなある? 3000 円損した。\n#PR"
    report = validate_bluesky_post(body, PostMode.preparation)
    assert "bluesky.pr_tag_in_preparation" in _rule_ids(report, ValidationSeverity.warning)


def test_affiliate_without_numbers_info() -> None:
    body = "この商品買ってよかった。洗いやすいし軽い。\n#時短家事 #PR"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.no_concrete_spec" in _rule_ids(report, ValidationSeverity.info)


def test_affiliate_with_numbers_no_info() -> None:
    body = "600ml 1 分半で沸く、80g で軽い。\n#時短家事 #PR"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.no_concrete_spec" not in _rule_ids(report)


def test_multiple_urls_info() -> None:
    body = "比較してみた。\n" "https://a.example.com/\n" "https://b.example.com/\n" "#買い物 #PR"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.multiple_urls" in _rule_ids(report, ValidationSeverity.info)


def test_single_url_no_info() -> None:
    body = "600ml で 1 分半。\nhttps://a.example.com/\n#時短家事 #PR"
    report = validate_bluesky_post(body, PostMode.affiliate)
    assert "bluesky.multiple_urls" not in _rule_ids(report)


@pytest.mark.parametrize(
    "body",
    [
        "あ" * BLUESKY_MAX_CHARS,  # 300 chars = OK
        "あ" * (BLUESKY_MAX_CHARS + 1),  # 301 chars = error
    ],
)
def test_char_limit_boundary(body: str) -> None:
    report = validate_bluesky_post(body, PostMode.preparation)
    rule_ids = _rule_ids(report, ValidationSeverity.error)
    if len(body) > BLUESKY_MAX_CHARS:
        assert "bluesky.too_long" in rule_ids
    else:
        assert "bluesky.too_long" not in rule_ids


def test_bluesky_allows_url_in_body() -> None:
    """Unlike Threads, Bluesky does NOT penalize URLs in parent posts."""
    body = (
        "600ml で 1 分半の電気ケトル、神。\n" "https://item.rakuten.co.jp/shop/x/\n" "#時短家事 #PR"
    )
    report = validate_bluesky_post(body, PostMode.affiliate)
    ids = _rule_ids(report)
    assert "threads.url_in_parent" not in ids
    assert "bluesky.url_in_parent" not in ids  # no such rule
