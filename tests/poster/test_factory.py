from __future__ import annotations

from aya_afi.config.settings import Settings
from aya_afi.poster.bluesky import BlueskyPoster
from aya_afi.poster.factory import create_poster
from aya_afi.poster.mock import MockPoster
from aya_afi.poster.note_clipboard import NoteClipboardPoster
from aya_afi.poster.threads import ThreadsPoster
from aya_afi.sns_engine.base import SnsKind


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "llm_provider": "mock",
        "threads_access_token": None,
        "threads_user_id": None,
        "bluesky_handle": None,
        "bluesky_app_password": None,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_note_always_uses_clipboard_poster() -> None:
    poster = create_poster(SnsKind.note, _settings())
    assert isinstance(poster, NoteClipboardPoster)


def test_threads_without_credentials_falls_back_to_mock() -> None:
    poster = create_poster(SnsKind.threads, _settings())
    assert isinstance(poster, MockPoster)


def test_threads_with_full_credentials_uses_real_poster() -> None:
    poster = create_poster(
        SnsKind.threads,
        _settings(threads_access_token="tkn", threads_user_id="uid"),
    )
    assert isinstance(poster, ThreadsPoster)


def test_threads_with_partial_credentials_falls_back_to_mock() -> None:
    # Token but no user_id → not enough to make real API calls.
    poster = create_poster(SnsKind.threads, _settings(threads_access_token="tkn"))
    assert isinstance(poster, MockPoster)


def test_bluesky_without_credentials_falls_back_to_mock() -> None:
    poster = create_poster(SnsKind.bluesky, _settings())
    assert isinstance(poster, MockPoster)


def test_bluesky_with_credentials_uses_real_poster() -> None:
    poster = create_poster(
        SnsKind.bluesky,
        _settings(bluesky_handle="aya.bsky.social", bluesky_app_password="abcd-efgh"),
    )
    assert isinstance(poster, BlueskyPoster)
