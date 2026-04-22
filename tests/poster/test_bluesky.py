from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aya_afi.poster.base import PostRequest
from aya_afi.poster.bluesky import BlueskyPoster
from aya_afi.poster.errors import PosterAPIError, PosterAuthError, PosterConfigError
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
