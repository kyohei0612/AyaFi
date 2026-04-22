"""note "posting" via clipboard (no automation, ADR-006 case 3).

Copies the body to the OS clipboard so the wife can paste it into her note
new-post page. The Tauri shell command opens the browser separately.

This module exists inside the Poster abstraction so note is a first-class
target alongside Threads / Bluesky from the caller's perspective, even though
the actual "send" is the wife pressing Ctrl+V and clicking 公開.
"""

from __future__ import annotations

import logging

from aya_afi.poster.base import PostRequest, PostResult
from aya_afi.poster.errors import PosterAPIError

_log = logging.getLogger("aya_afi.poster.note")

NOTE_COMPOSE_URL = "https://note.com/notes/new"


class NoteClipboardPoster:
    """Copies body to clipboard; opening note.com is a Tauri-side concern."""

    name = "note"

    async def publish(self, req: PostRequest) -> PostResult:
        if req.dry_run:
            _log.info(
                "note_dry_run",
                extra={
                    "event": "note_dry_run",
                    "char_count": len(req.body),
                    "image_count": len(req.image_paths),
                },
            )
            return PostResult(success=True, sns=req.sns, sns_post_url=NOTE_COMPOSE_URL)

        try:
            import pyperclip

            pyperclip.copy(req.body)
        except Exception as e:
            raise PosterAPIError(f"failed to copy to clipboard: {e}") from e

        _log.info(
            "note_clipboard_copied",
            extra={
                "event": "note_clipboard_copied",
                "char_count": len(req.body),
                "image_count_manual": len(req.image_paths),
            },
        )
        return PostResult(
            success=True,
            sns=req.sns,
            # The wife will land on this URL via `open_note_compose` Tauri cmd;
            # we surface it here so the UI / storage can record a stable link.
            sns_post_url=NOTE_COMPOSE_URL,
        )
