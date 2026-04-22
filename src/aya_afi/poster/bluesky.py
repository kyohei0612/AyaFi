"""Bluesky (atproto) poster — real implementation (Stage 3.b).

Uses the official ``atproto`` SDK. Because the sync ``Client`` is the more
stable API surface, we wrap blocking calls in ``asyncio.to_thread`` to keep
our IPC handler non-blocking.

ADR-005 note: Bluesky has NO server-side idempotency / client_token
mechanism, so duplicate-post prevention relies entirely on ``storage``'s
5-minute application-level block (Layer 1).

Image attachment lands in a follow-up (Stage 3.c) — for now text-only posts.
"""

from __future__ import annotations

import asyncio
import logging

from aya_afi.poster.base import PostRequest, PostResult
from aya_afi.poster.errors import (
    PosterAPIError,
    PosterAuthError,
    PosterConfigError,
    PosterRateLimitError,
)

_log = logging.getLogger("aya_afi.poster.bluesky")

_PROFILE_URL_TEMPLATE = "https://bsky.app/profile/{handle}/post/{rkey}"


class BlueskyPoster:
    name = "bluesky"

    def __init__(self, handle: str, app_password: str) -> None:
        if not handle:
            raise PosterConfigError("Bluesky poster requires BLUESKY_HANDLE in .env")
        if not app_password:
            raise PosterConfigError(
                "Bluesky poster requires BLUESKY_APP_PASSWORD in .env " "(Bluesky 設定画面で発行)"
            )
        self._handle = handle
        self._app_password = app_password

    async def publish(self, req: PostRequest) -> PostResult:
        if req.dry_run:
            return self._dry_run_result(req)
        try:
            uri = await asyncio.to_thread(self._blocking_publish, req.body)
        except PosterAPIError:
            raise
        except Exception as e:
            raise _translate_error(e) from e

        rkey = uri.rsplit("/", 1)[-1]
        url = _PROFILE_URL_TEMPLATE.format(handle=self._handle, rkey=rkey)
        _log.info(
            "bluesky_post_success",
            extra={
                "event": "bluesky_post_success",
                "idempotency_key": req.idempotency_key,
                "uri": uri,
            },
        )
        return PostResult(
            success=True,
            sns=req.sns,
            sns_post_id=uri,
            sns_post_url=url,
        )

    def _blocking_publish(self, body: str) -> str:
        """Run the atproto sync flow in a worker thread.

        Returns the new post's AT URI (``at://did:.../app.bsky.feed.post/rkey``).
        """
        # Lazy import: keeps the module loadable without the SDK in test envs.
        from atproto import Client

        client = Client()
        try:
            client.login(self._handle, self._app_password)
        except Exception as e:
            raise PosterAuthError(f"Bluesky login failed: {e}") from e

        resp = client.send_post(text=body)
        return str(resp.uri)

    def _dry_run_result(self, req: PostRequest) -> PostResult:
        _log.info(
            "bluesky_dry_run",
            extra={
                "event": "bluesky_dry_run",
                "char_count": len(req.body),
                "image_count": len(req.image_paths),
                "idempotency_key": req.idempotency_key,
            },
        )
        post_id = f"dry-run-{req.idempotency_key[:8]}"
        return PostResult(
            success=True,
            sns=req.sns,
            sns_post_id=post_id,
            sns_post_url=_PROFILE_URL_TEMPLATE.format(handle=self._handle, rkey=post_id),
        )


def _translate_error(e: BaseException) -> Exception:
    """Best-effort mapping of atproto exceptions to ``PosterError`` types."""
    message = str(e)
    lowered = message.lower()
    if "rate" in lowered and "limit" in lowered:
        return PosterRateLimitError(message)
    if "auth" in lowered or "credential" in lowered or "401" in lowered:
        return PosterAuthError(message)
    return PosterAPIError(message)
