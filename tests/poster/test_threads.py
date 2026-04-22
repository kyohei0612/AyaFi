from __future__ import annotations

from typing import Any

import httpx
import pytest

from aya_afi.poster.base import PostRequest
from aya_afi.poster.errors import (
    PosterAPIError,
    PosterAuthError,
    PosterConfigError,
    PosterRateLimitError,
    PosterValidationError,
)
from aya_afi.poster.threads import GRAPH_API_BASE, ThreadsPoster
from aya_afi.sns_engine.base import SnsKind


def _req(**overrides: Any) -> PostRequest:
    defaults: dict[str, Any] = {
        "sns": SnsKind.threads,
        "body": "hello threads world",
        "idempotency_key": "test-key-1",
    }
    defaults.update(overrides)
    return PostRequest.model_validate(defaults)


def _poster() -> ThreadsPoster:
    return ThreadsPoster(access_token="tok", user_id="user-1")


def _handler_factory(responses: list[httpx.Response]) -> Any:
    """Return a MockTransport handler that pops from ``responses`` per call."""
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(iterator)

    return handler


def _install_mock(monkeypatch: pytest.MonkeyPatch, responses: list[httpx.Response]) -> None:
    transport = httpx.MockTransport(_handler_factory(responses))
    orig_init = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)


def test_missing_token_rejected() -> None:
    with pytest.raises(PosterConfigError, match="THREADS_ACCESS_TOKEN"):
        ThreadsPoster(access_token="", user_id="u")


def test_missing_user_id_rejected() -> None:
    with pytest.raises(PosterConfigError, match="THREADS_USER_ID"):
        ThreadsPoster(access_token="t", user_id="")


async def test_dry_run_skips_network() -> None:
    result = await _poster().publish(_req(dry_run=True))
    assert result.success is True
    assert result.sns == SnsKind.threads
    assert result.sns_post_id is not None
    assert result.reply_post_id is None


async def test_dry_run_with_reply_returns_both_ids() -> None:
    result = await _poster().publish(_req(dry_run=True, reply_body="reply https://link"))
    assert result.reply_post_id is not None


async def test_publish_text_only_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock(
        monkeypatch,
        [
            httpx.Response(200, json={"id": "container-1"}),
            httpx.Response(200, json={"id": "post-1"}),
            httpx.Response(
                200,
                json={"id": "post-1", "permalink": "https://www.threads.net/@u/post/abc"},
            ),
        ],
    )
    result = await _poster().publish(_req())
    assert result.success is True
    assert result.sns_post_id == "post-1"
    assert result.sns_post_url == "https://www.threads.net/@u/post/abc"
    assert result.reply_post_id is None


async def test_publish_with_reply_issues_four_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        # 4 calls: parent create, parent publish, reply create, reply publish, permalink
        idx = len(calls)
        if idx == 1:
            return httpx.Response(200, json={"id": "parent-container"})
        if idx == 2:
            return httpx.Response(200, json={"id": "parent-post"})
        if idx == 3:
            return httpx.Response(200, json={"id": "reply-container"})
        if idx == 4:
            return httpx.Response(200, json={"id": "reply-post"})
        return httpx.Response(200, json={"permalink": "https://www.threads.net/@u/post/xyz"})

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    result = await _poster().publish(_req(reply_body="reply https://aff-link"))
    assert result.success is True
    assert result.sns_post_id == "parent-post"
    assert result.reply_post_id == "reply-post"

    # Reply container create must include reply_to_id referencing the parent.
    reply_create = calls[2]
    assert "reply_to_id=parent-post" in str(reply_create.url)
    # Parent container must NOT have reply_to_id.
    parent_create = calls[0]
    assert "reply_to_id" not in str(parent_create.url)


async def test_auth_failure_maps_to_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock(
        monkeypatch,
        [
            httpx.Response(
                400,
                json={"error": {"code": 190, "message": "Invalid OAuth access token"}},
            ),
        ],
    )
    with pytest.raises(PosterAuthError, match="190"):
        await _poster().publish(_req())


async def test_rate_limit_maps_to_rate_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock(
        monkeypatch,
        [
            httpx.Response(
                429,
                headers={"Retry-After": "120"},
                json={"error": {"code": 4, "message": "rate limit"}},
            ),
        ],
    )
    with pytest.raises(PosterRateLimitError) as exc_info:
        await _poster().publish(_req())
    assert exc_info.value.retry_after_sec == 120.0


async def test_server_error_maps_to_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock(
        monkeypatch,
        [httpx.Response(503, json={"error": {"message": "backend down"}})],
    )
    with pytest.raises(PosterAPIError, match="503"):
        await _poster().publish(_req())


async def test_content_rejection_maps_to_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock(
        monkeypatch,
        [
            httpx.Response(
                400,
                json={"error": {"code": 100, "message": "Post contains prohibited content"}},
            ),
        ],
    )
    with pytest.raises(PosterValidationError, match="100"):
        await _poster().publish(_req())


async def test_publish_url_targets_correct_user(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"id": "c"})
        if len(calls) == 2:
            return httpx.Response(200, json={"id": "p"})
        return httpx.Response(200, json={"permalink": None})

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    await _poster().publish(_req())
    assert all(GRAPH_API_BASE in str(c.url) for c in calls)
    assert "/user-1/threads" in str(calls[0].url)
    assert "/user-1/threads_publish" in str(calls[1].url)


async def test_permalink_failure_does_not_fail_post(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock(
        monkeypatch,
        [
            httpx.Response(200, json={"id": "c"}),
            httpx.Response(200, json={"id": "p"}),
            httpx.Response(500, json={"error": {"message": "gone"}}),
        ],
    )
    result = await _poster().publish(_req())
    assert result.success is True
    assert result.sns_post_id == "p"
    assert result.sns_post_url is None
