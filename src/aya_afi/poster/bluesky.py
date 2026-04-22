"""Bluesky (atproto) poster.

Stage 1 scope: constructor + config validation + dry-run path.
Real atproto calls land in **Stage 3.b**.

Bluesky doesn't have a client_token / idempotency mechanism, so dedup relies
entirely on the app-side 5-minute block from ADR-005 §Layer 1.
"""

from __future__ import annotations

import logging

from aya_afi.poster.base import PostRequest, PostResult
from aya_afi.poster.errors import PosterConfigError

_log = logging.getLogger("aya_afi.poster.bluesky")


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
        # TODO Stage 3.b: implement via `atproto` SDK
        #   client = AtprotoClient()
        #   client.login(handle, app_password)
        #   client.send_post(text=req.body, embed=images)
        raise NotImplementedError("Stage 3.b will implement the actual Bluesky atproto flow.")

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
            sns_post_url=f"https://bsky.app/profile/{self._handle}/post/{post_id}",
        )
