from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aya_afi.poster.base import PostRequest
from aya_afi.poster.bluesky import BlueskyPoster, _build_rich_text
from aya_afi.poster.errors import (
    PosterAPIError,
    PosterAuthError,
    PosterConfigError,
    PosterValidationError,
)
from aya_afi.sns_engine.base import SnsKind


def _req(**overrides: Any) -> PostRequest:
    defaults: dict[str, Any] = {
        "sns": SnsKind.bluesky,
        "body": "hello bluesky world",
        "idempotency_key": "test-key-1",
    }
    defaults.update(overrides)
    return PostRequest.model_validate(defaults)


def test_missing_handle_rejected() -> None:
    with pytest.raises(PosterConfigError, match="BLUESKY_HANDLE"):
        BlueskyPoster(handle="", app_password="x")


def test_missing_password_rejected() -> None:
    with pytest.raises(PosterConfigError, match="BLUESKY_APP_PASSWORD"):
        BlueskyPoster(handle="a.bsky.social", app_password="")


async def test_dry_run_skips_network() -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")
    result = await poster.publish(_req(dry_run=True))
    assert result.success is True
    assert result.sns == SnsKind.bluesky
    assert result.sns_post_url is not None
    assert "aya.bsky.social" in result.sns_post_url


async def test_publish_success_returns_post_url() -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.uri = "at://did:plc:abc/app.bsky.feed.post/RKEY123"
    fake_client.send_post.return_value = fake_resp

    with patch("atproto.Client", return_value=fake_client):
        result = await poster.publish(_req())

    assert result.success is True
    assert result.sns_post_id == "at://did:plc:abc/app.bsky.feed.post/RKEY123"
    assert result.sns_post_url == "https://bsky.app/profile/aya.bsky.social/post/RKEY123"
    fake_client.login.assert_called_once_with("aya.bsky.social", "app-pw")
    fake_client.send_post.assert_called_once()


async def test_publish_login_failure_maps_to_auth_error() -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="bad-pw")

    fake_client = MagicMock()
    fake_client.login.side_effect = RuntimeError("invalid credentials")

    with (
        patch("atproto.Client", return_value=fake_client),
        pytest.raises(PosterAuthError, match="login failed"),
    ):
        await poster.publish(_req())


async def test_publish_post_api_failure_maps_to_api_error() -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")

    fake_client = MagicMock()
    fake_client.send_post.side_effect = RuntimeError("internal 500")

    with (
        patch("atproto.Client", return_value=fake_client),
        pytest.raises(PosterAPIError, match="500"),
    ):
        await poster.publish(_req())


async def test_publish_rate_limit_maps_to_rate_limit_error() -> None:
    from aya_afi.poster.errors import PosterRateLimitError

    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")

    fake_client = MagicMock()
    fake_client.send_post.side_effect = RuntimeError("rate limit exceeded")

    with (
        patch("atproto.Client", return_value=fake_client),
        pytest.raises(PosterRateLimitError),
    ):
        await poster.publish(_req())


class _StubBuilder:
    """Minimal TextBuilder stand-in that records calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def text(self, s: str) -> _StubBuilder:
        self.calls.append(("text", (s,)))
        return self

    def tag(self, display: str, tag: str) -> _StubBuilder:
        self.calls.append(("tag", (display, tag)))
        return self


def test_rich_text_splits_plain_and_hashtags() -> None:
    tb = _StubBuilder()
    _build_rich_text("こんにちは #節約 #暮らし", tb)
    assert tb.calls == [
        ("text", ("こんにちは ",)),
        ("tag", ("#節約", "節約")),
        ("text", (" ",)),
        ("tag", ("#暮らし", "暮らし")),
    ]


def test_rich_text_no_tags_produces_single_text_segment() -> None:
    tb = _StubBuilder()
    _build_rich_text("ただの本文です。", tb)
    assert tb.calls == [("text", ("ただの本文です。",))]


def test_rich_text_tag_at_start_and_end() -> None:
    tb = _StubBuilder()
    _build_rich_text("#start 本文 #end", tb)
    assert tb.calls == [
        ("tag", ("#start", "start")),
        ("text", (" 本文 ",)),
        ("tag", ("#end", "end")),
    ]


def test_rich_text_japanese_hashtag() -> None:
    tb = _StubBuilder()
    _build_rich_text("#節約生活 のヒント", tb)
    # Japanese characters must be captured into the tag.
    assert tb.calls[0] == ("tag", ("#節約生活", "節約生活"))


async def test_too_many_images_rejected_as_validation_error(tmp_path: Any) -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")
    paths = []
    for i in range(5):
        p = tmp_path / f"img{i}.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        paths.append(str(p))

    fake_client = MagicMock()
    fake_client.upload_blob.return_value = MagicMock(blob="BLOB")

    with (
        patch("atproto.Client", return_value=fake_client),
        pytest.raises(PosterValidationError, match="4 枚まで"),
    ):
        await poster.publish(_req(image_paths=paths))


async def test_missing_image_file_raises_validation(tmp_path: Any) -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")
    missing = str(tmp_path / "does-not-exist.jpg")

    fake_client = MagicMock()

    with (
        patch("atproto.Client", return_value=fake_client),
        pytest.raises(PosterValidationError, match="見つかりません"),
    ):
        await poster.publish(_req(image_paths=[missing]))


async def test_oversized_image_raises_validation(tmp_path: Any) -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")
    too_big = tmp_path / "huge.jpg"
    too_big.write_bytes(b"\x00" * (977 * 1024))  # > 976 KB

    fake_client = MagicMock()

    with (
        patch("atproto.Client", return_value=fake_client),
        pytest.raises(PosterValidationError, match="大きすぎます"),
    ):
        await poster.publish(_req(image_paths=[str(too_big)]))


async def test_images_are_uploaded_and_embedded(tmp_path: Any) -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")
    path_a = tmp_path / "a.jpg"
    path_a.write_bytes(b"AAAA")
    path_b = tmp_path / "b.jpg"
    path_b.write_bytes(b"BBBB")

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.uri = "at://did:plc:abc/app.bsky.feed.post/R"
    fake_client.send_post.return_value = fake_resp
    fake_client.upload_blob.side_effect = [
        MagicMock(blob="BLOB_A"),
        MagicMock(blob="BLOB_B"),
    ]

    captured_embed: dict[str, Any] = {}

    def capture(text: Any, embed: Any = None) -> Any:
        captured_embed["embed"] = embed
        return fake_resp

    fake_client.send_post.side_effect = capture

    class _FakeImage:
        def __init__(self, alt: str, image: Any) -> None:
            self.alt = alt
            self.image = image

    class _FakeMain:
        def __init__(self, images: list[Any]) -> None:
            self.images = images

    fake_models = MagicMock()
    fake_models.AppBskyEmbedImages.Image.side_effect = _FakeImage
    fake_models.AppBskyEmbedImages.Main.side_effect = _FakeMain

    with (
        patch("atproto.Client", return_value=fake_client),
        patch("atproto.models", fake_models),
    ):
        await poster.publish(_req(image_paths=[str(path_a), str(path_b)]))

    assert fake_client.upload_blob.call_count == 2
    fake_client.upload_blob.assert_any_call(b"AAAA")
    fake_client.upload_blob.assert_any_call(b"BBBB")
    embed = captured_embed["embed"]
    assert [img.image for img in embed.images] == ["BLOB_A", "BLOB_B"]


async def test_full_width_hash_is_normalized_before_tag_extraction() -> None:
    """`＃tag` (LLM output) should be routed as a proper hashtag facet."""
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="app-pw")

    captured: dict[str, Any] = {}
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.uri = "at://did:plc:abc/app.bsky.feed.post/R"
    fake_client.send_post.return_value = fake_resp

    # Spy on TextBuilder so we can inspect what facet segments were emitted.
    recorder = _StubBuilder()

    class _FakeUtils:
        @staticmethod
        def TextBuilder() -> _StubBuilder:  # noqa: N802
            return recorder

    def capture(text: Any, embed: Any = None) -> Any:
        captured["text"] = text
        return fake_resp

    fake_client.send_post.side_effect = capture

    with (
        patch("atproto.Client", return_value=fake_client),
        patch("atproto.client_utils", _FakeUtils),
    ):
        await poster.publish(_req(body="本文 ＃節約 あとから"))

    # The full-width `＃` became a half-width `#` tag.
    tag_calls = [c for c in recorder.calls if c[0] == "tag"]
    assert tag_calls == [("tag", ("#節約", "節約"))]
