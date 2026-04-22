"""Every real Poster stub must support ``dry_run=True`` without raising.

This prevents Stage 3 from accidentally regressing the dry-run path when the
real API implementations land.
"""

from __future__ import annotations

from aya_afi.poster.base import PostRequest
from aya_afi.poster.bluesky import BlueskyPoster
from aya_afi.poster.note_clipboard import NoteClipboardPoster
from aya_afi.poster.threads import ThreadsPoster
from aya_afi.sns_engine.base import SnsKind


def _req(sns: SnsKind, **overrides: object) -> PostRequest:
    defaults: dict[str, object] = {
        "sns": sns,
        "body": "dry run body",
        "idempotency_key": "dry-run-key",
        "dry_run": True,
    }
    defaults.update(overrides)
    return PostRequest.model_validate(defaults)


async def test_threads_dry_run_logs_and_returns_success() -> None:
    poster = ThreadsPoster(access_token="fake", user_id="fake")
    result = await poster.publish(_req(SnsKind.threads, reply_body="aff url"))
    assert result.success is True
    assert result.sns_post_id is not None
    assert result.reply_post_id is not None


async def test_bluesky_dry_run_returns_success() -> None:
    poster = BlueskyPoster(handle="aya.bsky.social", app_password="abcd-efgh")
    result = await poster.publish(_req(SnsKind.bluesky))
    assert result.success is True
    assert result.sns_post_id is not None
    assert result.sns_post_url is not None


async def test_note_dry_run_returns_success() -> None:
    poster = NoteClipboardPoster()
    result = await poster.publish(_req(SnsKind.note))
    assert result.success is True
