"""Bluesky (atproto) poster — real implementation (Stage 3.b + 3.c).

Uses the official ``atproto`` SDK. Because the sync ``Client`` is the more
stable API surface, we wrap blocking calls in ``asyncio.to_thread`` to keep
our IPC handler non-blocking.

ADR-005 note: Bluesky has NO server-side idempotency / client_token
mechanism, so duplicate-post prevention relies entirely on ``storage``'s
5-minute application-level block (Layer 1).

Hashtag handling: ``client.send_post(text=<str>)`` sends plain text without
facets, so ``#foo`` would not become a clickable / searchable tag. We use
``TextBuilder`` to emit proper ``app.bsky.richtext.facet#tag`` segments so
hashtags get picked up by custom feeds (which is the whole point of
``tagLabel: "タグ 2-4 個"`` in the UI). Full-width ``＃`` is normalized to
half-width ``#`` first, since LLMs mix both in Japanese output.

Image attachment (Stage 3.c): Bluesky accepts direct binary uploads via
``upload_blob`` (<1 MB per image, max 4 images). We read the picked files
from disk, upload each, and attach the returned blobs as an
``app.bsky.embed.images`` embed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from aya_afi.poster.base import PostRequest, PostResult
from aya_afi.poster.errors import (
    PosterAPIError,
    PosterAuthError,
    PosterConfigError,
    PosterRateLimitError,
    PosterValidationError,
)

# Bluesky limits (blob size, image count): `upload_blob` rejects > ~1 MB.
_MAX_IMAGE_BYTES = 976 * 1024
_MAX_IMAGES = 4

# Matches ``#tag`` where the tag contains letters/digits/underscore + any
# JP-range code points. Stops at whitespace, ASCII punctuation, or EOS.
# Excludes surrounding ``#`` so overlapping doesn't matter.
_HASHTAG_RE = re.compile(r"#([^\s#!-/:-@\[-`{-~]+)")

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
            uri = await asyncio.to_thread(
                self._blocking_publish, req.body, req.image_paths
            )
        except (PosterAPIError, PosterValidationError):
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

    def _blocking_publish(self, body: str, image_paths: list[str]) -> str:
        """Run the atproto sync flow in a worker thread.

        Returns the new post's AT URI (``at://did:.../app.bsky.feed.post/rkey``).
        """
        # Lazy import: keeps the module loadable without the SDK in test envs.
        from atproto import Client, client_utils, models

        normalized = body.replace("\uff03", "#")
        text = _build_rich_text(normalized, client_utils.TextBuilder())

        client = Client()
        try:
            client.login(self._handle, self._app_password)
        except Exception as e:
            raise PosterAuthError(f"Bluesky login failed: {e}") from e

        embed = None
        if image_paths:
            embed = self._upload_images(client, models, image_paths)

        resp = client.send_post(text=text, embed=embed)
        return str(resp.uri)

    def _upload_images(self, client: object, models: object, paths: list[str]) -> object:
        """Upload each image blob and return an ``embed.images`` record.

        Validation errors (missing file, oversize) are mapped to
        ``PosterValidationError`` so the IPC layer surfaces them as
        user-fixable issues rather than opaque API failures.
        """
        if len(paths) > _MAX_IMAGES:
            raise PosterValidationError(
                f"Bluesky は 1 投稿に画像 {_MAX_IMAGES} 枚までです "
                f"(今回 {len(paths)} 枚指定)。"
            )
        image_records: list[object] = []
        for p in paths:
            path = Path(p)
            if not path.is_file():
                raise PosterValidationError(f"画像が見つかりません: {p}")
            data = path.read_bytes()
            if len(data) > _MAX_IMAGE_BYTES:
                raise PosterValidationError(
                    f"画像が大きすぎます (Bluesky 上限 976 KB): "
                    f"{path.name} = {len(data) // 1024} KB"
                )
            blob = client.upload_blob(data).blob  # type: ignore[attr-defined]
            image_records.append(
                models.AppBskyEmbedImages.Image(alt="", image=blob)  # type: ignore[attr-defined]
            )
        return models.AppBskyEmbedImages.Main(images=image_records)  # type: ignore[attr-defined]

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


def _build_rich_text(body: str, tb: object) -> object:
    """Split ``body`` into literal text and ``#tag`` segments on ``tb``.

    Uses atproto's ``TextBuilder`` so each hashtag becomes a proper
    ``app.bsky.richtext.facet#tag`` facet (clickable, surfaced to feeds).
    The ``tb`` parameter is injected so the heavy ``atproto`` import stays
    lazy — the caller constructs the builder after the SDK is available.
    """
    cursor = 0
    for match in _HASHTAG_RE.finditer(body):
        start, end = match.span()
        if start > cursor:
            tb.text(body[cursor:start])  # type: ignore[attr-defined]
        tb.tag(match.group(0), match.group(1))  # type: ignore[attr-defined]
        cursor = end
    if cursor < len(body):
        tb.text(body[cursor:])  # type: ignore[attr-defined]
    return tb
