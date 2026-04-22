"""Threads (Meta Graph API) poster.

Stage 1 scope (current): constructor + config validation + dry-run path.
Real API calls land in **Stage 3.a**. Structure is locked in now so ADR-005's
``post_targets`` state machine can depend on a stable ``publish`` contract.

2-step posting design (ADR-012 §2):
    1. Create parent-post media container (if images)
    2. Create parent post (body only, NO URL)
    3. Publish parent → obtain parent_id
    4. If reply_body: create reply-post container referencing parent_id
    5. Publish reply (affiliate URL lives here)
"""

from __future__ import annotations

import logging

from aya_afi.poster.base import PostRequest, PostResult
from aya_afi.poster.errors import PosterConfigError

_log = logging.getLogger("aya_afi.poster.threads")

GRAPH_API_BASE = "https://graph.threads.net/v1.0"


class ThreadsPoster:
    name = "threads"

    def __init__(self, access_token: str, user_id: str) -> None:
        if not access_token:
            raise PosterConfigError(
                "Threads poster requires THREADS_ACCESS_TOKEN in .env "
                "(Meta 開発者 → Threads アプリ → ユーザーアクセストークン)"
            )
        if not user_id:
            raise PosterConfigError("Threads poster requires THREADS_USER_ID in .env")
        self._access_token = access_token
        self._user_id = user_id

    async def publish(self, req: PostRequest) -> PostResult:
        if req.dry_run:
            return self._dry_run_result(req)
        # TODO Stage 3.a: implement 2-step posting
        #   step1 = POST /{user_id}/threads (body + media_ids, no URL)
        #   step2 = POST /{user_id}/threads_publish (returns parent_id)
        #   step3 = POST /{user_id}/threads (reply_to_id=parent_id, reply_body w/ URL)
        #   step4 = POST /{user_id}/threads_publish
        # Use req.idempotency_key as client_token where supported.
        raise NotImplementedError("Stage 3.a will implement the actual Threads Graph API flow.")

    def _dry_run_result(self, req: PostRequest) -> PostResult:
        _log.info(
            "threads_dry_run",
            extra={
                "event": "threads_dry_run",
                "char_count": len(req.body),
                "has_reply": req.reply_body is not None,
                "image_count": len(req.image_paths),
                "idempotency_key": req.idempotency_key,
            },
        )
        post_id = f"dry-run-{req.idempotency_key[:8]}"
        reply_id = f"{post_id}-reply" if req.reply_body else None
        return PostResult(
            success=True,
            sns=req.sns,
            sns_post_id=post_id,
            sns_post_url=f"https://www.threads.net/@user/post/{post_id}",
            reply_post_id=reply_id,
        )
