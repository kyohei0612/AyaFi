"""Anonymous image hosting for Threads API requirement.

Threads' Graph API does not accept direct binary image uploads; it needs a
publicly reachable HTTPS URL. For a Windows-local desktop app without its
own cloud infrastructure, the lowest-friction option is an anonymous
paste/upload service.

Primary provider: **catbox.moe** (no API key, permanent URLs).
Fallback provider: **0x0.st** (no API key, 30-day retention) — used when
catbox returns 4xx/5xx (their storage outages are frequent). Threads
caches the image once it has been fetched, so a 30-day URL is enough.

Tradeoff: uploaded images are publicly accessible to anyone with the URL.
For affiliate product photos this is acceptable; the same images end up
on Threads CDNs anyway.

Failures map to ``PosterValidationError`` (file) or ``PosterAPIError``
(all hosts down / rejected) so the poster layer can translate them into
IPC error types the UI already knows how to display.
"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from aya_afi.poster.errors import PosterAPIError, PosterValidationError

_log = logging.getLogger("aya_afi.poster.image_host")

_CATBOX_ENDPOINT = "https://catbox.moe/user/api.php"
_NULLPOINTER_ENDPOINT = "https://0x0.st"
_UPLOAD_TIMEOUT_SEC = 60.0
# catbox accepts up to 200 MB for anonymous uploads, but Threads itself
# rejects oversize images silently, so clamp to a sensible SNS-scale limit.
_MAX_BYTES = 8 * 1024 * 1024


async def upload_image(path: str) -> str:
    """Upload ``path`` and return the resulting HTTPS URL.

    Tries catbox.moe first, then 0x0.st on failure. Raises
    ``PosterValidationError`` if the file is missing or too large, and
    ``PosterAPIError`` if all hosts fail.
    """
    p = Path(path)
    if not p.is_file():
        raise PosterValidationError(f"画像が見つかりません: {path}")
    data = p.read_bytes()
    if len(data) > _MAX_BYTES:
        raise PosterValidationError(
            f"画像が大きすぎます (Threads 経由の上限 8 MB): "
            f"{p.name} = {len(data) // (1024 * 1024)} MB"
        )

    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"

    providers: list[tuple[str, _UploaderFn]] = [
        ("catbox.moe", _upload_catbox),
        ("0x0.st", _upload_nullpointer),
    ]
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT_SEC) as client:
        for name, fn in providers:
            try:
                url = await fn(client, p.name, data, mime)
                _log.info(
                    "image_host_upload_ok",
                    extra={
                        "event": "image_host_upload_ok",
                        "provider": name,
                        "bytes": len(data),
                        "url": url,
                    },
                )
                return url
            except PosterAPIError as e:
                errors.append(f"{name}: {e}")
                _log.warning(
                    "image_host_upload_failed",
                    extra={
                        "event": "image_host_upload_failed",
                        "provider": name,
                        "error": str(e),
                    },
                )
    raise PosterAPIError("全画像ホスト失敗: " + " / ".join(errors))


_UploaderFn = Callable[[httpx.AsyncClient, str, bytes, str], Awaitable[str]]


async def _upload_catbox(
    client: httpx.AsyncClient, name: str, data: bytes, mime: str
) -> str:
    resp = await client.post(
        _CATBOX_ENDPOINT,
        data={"reqtype": "fileupload"},
        files={"fileToUpload": (name, data, mime)},
    )
    if resp.status_code != 200:
        raise PosterAPIError(
            f"catbox upload failed ({resp.status_code}): {resp.text[:200]}"
        )
    url = resp.text.strip()
    if not url.startswith("https://"):
        raise PosterAPIError(f"catbox returned unexpected payload: {url[:200]}")
    return url


async def _upload_nullpointer(
    client: httpx.AsyncClient, name: str, data: bytes, mime: str
) -> str:
    resp = await client.post(
        _NULLPOINTER_ENDPOINT,
        files={"file": (name, data, mime)},
        headers={"User-Agent": "AyaFi/0.1 (+https://github.com/kyohei0612/AyaFi)"},
    )
    if resp.status_code != 200:
        raise PosterAPIError(
            f"0x0.st upload failed ({resp.status_code}): {resp.text[:200]}"
        )
    url = resp.text.strip()
    if not url.startswith("https://"):
        raise PosterAPIError(f"0x0.st returned unexpected payload: {url[:200]}")
    return url
