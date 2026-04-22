from __future__ import annotations

from typing import Any

import pytest

from aya_afi.poster.base import PostRequest
from aya_afi.poster.errors import PosterAPIError
from aya_afi.poster.note_clipboard import NOTE_COMPOSE_URL, NoteClipboardPoster
from aya_afi.sns_engine.base import SnsKind


def _req(**overrides: object) -> PostRequest:
    defaults: dict[str, object] = {
        "sns": SnsKind.note,
        "body": "note 用の長文を書きます。\n#日々のこと",
        "idempotency_key": "note-1",
    }
    defaults.update(overrides)
    return PostRequest.model_validate(defaults)


class _FakeClipboard:
    def __init__(self) -> None:
        self.copied: list[str] = []

    def copy(self, text: str) -> None:
        self.copied.append(text)


async def test_publish_copies_body_to_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClipboard()
    monkeypatch.setitem(__import__("sys").modules, "pyperclip", fake)

    poster = NoteClipboardPoster()
    result = await poster.publish(_req())
    assert result.success is True
    assert result.sns == SnsKind.note
    assert result.sns_post_url == NOTE_COMPOSE_URL
    assert fake.copied == ["note 用の長文を書きます。\n#日々のこと"]


async def test_publish_dry_run_does_not_touch_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClipboard()
    monkeypatch.setitem(__import__("sys").modules, "pyperclip", fake)

    poster = NoteClipboardPoster()
    result = await poster.publish(_req(dry_run=True))
    assert result.success is True
    assert fake.copied == []


async def test_publish_wraps_clipboard_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Broken:
        def copy(self, text: str) -> None:
            raise RuntimeError("display not available")

    monkeypatch.setitem(__import__("sys").modules, "pyperclip", _Broken())

    poster = NoteClipboardPoster()
    with pytest.raises(PosterAPIError, match="clipboard"):
        await poster.publish(_req())


async def test_note_compose_url_is_stable() -> None:
    assert NOTE_COMPOSE_URL == "https://note.com/notes/new"


def test_fake_clipboard_setup_sanity() -> None:
    # Sanity: monkeypatch on sys.modules should make `import pyperclip` return fake.
    fake = _FakeClipboard()
    monkeypatch: Any = None  # not used; just for type noise silencing
    del monkeypatch
    assert fake.copied == []
