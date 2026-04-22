"""Anonymous image hosting via catbox.moe (Threads API requirement).

Threads' Graph API does not accept direct binary image uploads; it needs a
publicly reachable HTTPS URL. For a Windows-local desktop app without its
own cloud infrastructure, the lowest-friction option is an anonymous
paste/upload service. We use **catbox.moe** because:
    - no API key / account required
    - returns a stable ``https://files.catbox.moe/<id>.<ext>`` URL
    - files persist indefinitely (for anonymous uploads)
    - server-side TLS, reachable from Meta's fetchers

Tradeoff: uploaded images are publicly accessible to anyone with the URL.
For affiliate product photos this is acceptable; the same images end up
on Threads CDNs anyway.

Failures map to ``PosterValidationError`` (file) or ``PosterAPIError``
(host down / rejected) so the poster layer can translate them into IPC
error types the UI already knows how to display.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import httpx

from aya_afi.poster.errors import PosterAPIError, PosterValidationError

_log = logging.getLogger("aya_afi.poster.image_host")

_CATBOX_ENDPOINT = "https://catbox.moe/user/api.php"
_UPLOAD_TIMEOUT_SEC = 60.0
# catbox accepts up to 200 MB for anonymous uploads, but Threads itself
# rejects oversize images silently, so clamp to a sensible SNS-scale limit.
_MAX_BYTES = 8 * 1024 * 1024


async def upload_image(path: str) -> str:
    """Upload ``path`` to catbox.moe and return the resulting HTTPS URL.

    Raises ``PosterValidationError`` if the file is missing or too large,
    and ``PosterAPIError`` if catbox returns a non-URL response.
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
    files = {"fileToUpload": (p.name, data, mime)}
    form = {"reqtype": "fileupload"}

    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT_SEC) as client:
        resp = await client.post(_CATBOX_ENDPOINT, data=form, files=files)
    if resp.status_code != 200:
        raise PosterAPIError(
            f"catbox upload failed ({resp.status_code}): {resp.text[:200]}"
        )

    url = resp.text.strip()
    if not url.startswith("https://"):
        raise PosterAPIError(f"catbox returned unexpected payload: {url[:200]}")
    _log.info(
        "image_host_upload_ok",
        extra={"event": "image_host_upload_ok", "bytes": len(data), "url": url},
    )
    return url
