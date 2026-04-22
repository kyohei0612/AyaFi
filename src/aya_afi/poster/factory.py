"""Factory: pick a ``Poster`` for a target SNS based on settings.

Returns the real poster when credentials are present, otherwise falls back to
``MockPoster`` so the UI and Stage 5 storage can be developed without API
access.
"""

from __future__ import annotations

from aya_afi.config.settings import Settings
from aya_afi.poster.base import Poster
from aya_afi.poster.bluesky import BlueskyPoster
from aya_afi.poster.mock import MockPoster
from aya_afi.poster.note_clipboard import NoteClipboardPoster
from aya_afi.poster.threads import ThreadsPoster
from aya_afi.sns_engine.base import SnsKind


def create_poster(sns: SnsKind, settings: Settings) -> Poster:
    match sns:
        case SnsKind.note:
            # Always a local clipboard operation, no credentials needed.
            return NoteClipboardPoster()
        case SnsKind.threads:
            if not (settings.threads_access_token and settings.threads_user_id):
                return MockPoster()
            return ThreadsPoster(
                access_token=settings.threads_access_token,
                user_id=settings.threads_user_id,
            )
        case SnsKind.bluesky:
            if not (settings.bluesky_handle and settings.bluesky_app_password):
                return MockPoster()
            return BlueskyPoster(
                handle=settings.bluesky_handle,
                app_password=settings.bluesky_app_password,
            )
