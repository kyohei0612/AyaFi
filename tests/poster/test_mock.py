from __future__ import annotations

from aya_afi.poster.base import PostRequest
from aya_afi.poster.mock import MockPoster
from aya_afi.sns_engine.base import SnsKind


def _req(**overrides: object) -> PostRequest:
    defaults: dict[str, object] = {
        "sns": SnsKind.threads,
        "body": "hi",
        "idempotency_key": "11111111-2222-3333-4444-555555555555",
    }
    defaults.update(overrides)
    return PostRequest.model_validate(defaults)


async def test_mock_publish_success_by_default() -> None:
    poster = MockPoster()
    result = await poster.publish(_req())
    assert result.success is True
    assert result.sns_post_id is not None
    assert result.sns_post_url is not None
    assert result.error_type is None


async def test_mock_publish_with_reply_returns_reply_id() -> None:
    poster = MockPoster()
    result = await poster.publish(_req(reply_body="affiliate url"))
    assert result.reply_post_id is not None


async def test_mock_publish_without_reply_leaves_reply_id_none() -> None:
    poster = MockPoster()
    result = await poster.publish(_req())
    assert result.reply_post_id is None


async def test_mock_publish_failure_mode() -> None:
    poster = MockPoster(fail=True, fail_type="simulated_rate_limit")
    result = await poster.publish(_req())
    assert result.success is False
    assert result.error_type == "simulated_rate_limit"
    assert result.error_message is not None


async def test_mock_propagates_sns_kind() -> None:
    poster = MockPoster()
    result = await poster.publish(_req(sns=SnsKind.bluesky))
    assert result.sns == SnsKind.bluesky
