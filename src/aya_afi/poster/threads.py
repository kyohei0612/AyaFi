"""Threads (Meta Graph API) poster — real implementation (Stage 3.a + 3.c).

2-step posting design (ADR-012 §2):
    1. Create parent-post container (body only, NO URL) + optional images
    2. Publish parent → parent_id
    3. If reply_body: create reply container (reply_to_id=parent_id)
    4. Publish reply (affiliate URL lives here)

Images: Threads' Graph API only accepts public HTTPS image URLs, not direct
binary uploads. We first upload each local file via ``image_host`` (catbox
.moe), then reference the returned URLs. Single images use
``media_type=IMAGE``; 2+ images use the carousel flow (each item created
with ``is_carousel_item=true``, then a ``CAROUSEL`` container aggregates
them).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from aya_afi.poster.base import PostRequest, PostResult
from aya_afi.poster.errors import (
    PosterAPIError,
    PosterAuthError,
    PosterConfigError,
    PosterRateLimitError,
    PosterValidationError,
)
from aya_afi.poster.image_host import upload_image

_log = logging.getLogger("aya_afi.poster.threads")

GRAPH_API_BASE = "https://graph.threads.net/v1.0"
_REQUEST_TIMEOUT_SEC = 30.0


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

        image_urls: list[str] = []
        if req.image_paths:
            for p in req.image_paths:
                image_urls.append(await upload_image(p))

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SEC) as client:
            parent_id = await self._create_and_publish(
                client, req.body, reply_to_id=None, image_urls=image_urls
            )
            reply_id: str | None = None
            if req.reply_body:
                reply_id = await self._create_and_publish(
                    client, req.reply_body, reply_to_id=parent_id, image_urls=[]
                )
            permalink = await self._fetch_permalink(client, parent_id)

        _log.info(
            "threads_post_success",
            extra={
                "event": "threads_post_success",
                "idempotency_key": req.idempotency_key,
                "parent_id": parent_id,
                "reply_id": reply_id,
            },
        )
        return PostResult(
            success=True,
            sns=req.sns,
            sns_post_id=parent_id,
            sns_post_url=permalink,
            reply_post_id=reply_id,
        )

    async def _create_and_publish(
        self,
        client: httpx.AsyncClient,
        text: str,
        reply_to_id: str | None,
        image_urls: list[str],
    ) -> str:
        """Step 1+2 of the Threads posting flow. Returns the published post id.

        Dispatches on image count:
            - 0: text-only container (``media_type=TEXT``)
            - 1: single-image container (``media_type=IMAGE``)
            - 2+: carousel (per-image IMAGE items, then a CAROUSEL wrapper)
        """
        # Meta parses #tag server-side but only for half-width `#`; LLM output
        # commonly mixes full-width `＃`, so normalize before sending.
        normalized = text.replace("\uff03", "#")

        if not image_urls:
            container_id = await self._create_text_container(
                client, normalized, reply_to_id
            )
        elif len(image_urls) == 1:
            container_id = await self._create_image_container(
                client, normalized, image_urls[0], reply_to_id
            )
        else:
            container_id = await self._create_carousel_container(
                client, normalized, image_urls, reply_to_id
            )

        publish_resp = await client.post(
            f"{GRAPH_API_BASE}/{self._user_id}/threads_publish",
            params={"creation_id": container_id, "access_token": self._access_token},
        )
        return _parse_or_raise(publish_resp, field="id", step="publish")

    async def _create_text_container(
        self,
        client: httpx.AsyncClient,
        text: str,
        reply_to_id: str | None,
    ) -> str:
        params: dict[str, str] = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self._access_token,
        }
        if reply_to_id is not None:
            params["reply_to_id"] = reply_to_id
        resp = await client.post(
            f"{GRAPH_API_BASE}/{self._user_id}/threads", params=params
        )
        return _parse_or_raise(resp, field="id", step="create_container")

    async def _create_image_container(
        self,
        client: httpx.AsyncClient,
        text: str,
        image_url: str,
        reply_to_id: str | None,
    ) -> str:
        params: dict[str, str] = {
            "media_type": "IMAGE",
            "image_url": image_url,
            "text": text,
            "access_token": self._access_token,
        }
        if reply_to_id is not None:
            params["reply_to_id"] = reply_to_id
        resp = await client.post(
            f"{GRAPH_API_BASE}/{self._user_id}/threads", params=params
        )
        return _parse_or_raise(resp, field="id", step="create_image_container")

    async def _create_carousel_container(
        self,
        client: httpx.AsyncClient,
        text: str,
        image_urls: list[str],
        reply_to_id: str | None,
    ) -> str:
        item_ids: list[str] = []
        for url in image_urls:
            resp = await client.post(
                f"{GRAPH_API_BASE}/{self._user_id}/threads",
                params={
                    "media_type": "IMAGE",
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": self._access_token,
                },
            )
            item_ids.append(
                _parse_or_raise(resp, field="id", step="create_carousel_item")
            )

        params: dict[str, str] = {
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "text": text,
            "access_token": self._access_token,
        }
        if reply_to_id is not None:
            params["reply_to_id"] = reply_to_id
        resp = await client.post(
            f"{GRAPH_API_BASE}/{self._user_id}/threads", params=params
        )
        return _parse_or_raise(resp, field="id", step="create_carousel_container")

    async def _fetch_permalink(self, client: httpx.AsyncClient, post_id: str) -> str | None:
        """Best-effort: fetch the public permalink. Failure does NOT fail the post."""
        try:
            resp = await client.get(
                f"{GRAPH_API_BASE}/{post_id}",
                params={"fields": "permalink", "access_token": self._access_token},
            )
            if resp.status_code == 200:
                permalink = resp.json().get("permalink")
                return str(permalink) if permalink else None
        except httpx.HTTPError as e:
            _log.warning(
                "threads_permalink_fetch_failed",
                extra={"event": "threads_permalink_fetch_failed", "error": str(e)},
            )
        return None

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


def _parse_or_raise(resp: httpx.Response, *, field: str, step: str) -> str:
    """Extract ``field`` from a Threads API response, or raise the right PosterError."""
    if resp.status_code == 200:
        payload = resp.json()
        if field not in payload:
            raise PosterAPIError(
                f"Threads {step} returned 200 but no '{field}' field: {payload}"
            )
        return str(payload[field])
    raise _translate_error(resp, step=step)


def _translate_error(resp: httpx.Response, *, step: str) -> Exception:
    """Map a non-200 Threads response to the right PosterError subclass."""
    status = resp.status_code
    try:
        body: dict[str, Any] = resp.json()
    except ValueError:
        body = {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    code = error.get("code")
    subcode = error.get("error_subcode")
    message = error.get("message") or resp.text
    summary = f"Threads {step} failed ({status}, code={code}, sub={subcode}): {message}"

    # Auth: invalid/expired token (Meta codes 190, 452, 459, 463).
    if status == 401 or code in {190, 452, 459, 463, 467}:
        return PosterAuthError(summary)
    # Rate limit: 429 or Meta-specific codes 4, 17, 32, 613.
    if status == 429 or code in {4, 17, 32, 613}:
        retry_after = _extract_retry_after(resp)
        return PosterRateLimitError(summary, retry_after_sec=retry_after)
    # 5xx: transient/retryable.
    if status >= 500:
        return PosterAPIError(summary)
    # Other 4xx: content rejected (policy/length/media).
    if 400 <= status < 500:
        return PosterValidationError(summary)
    return PosterAPIError(summary)


def _extract_retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
