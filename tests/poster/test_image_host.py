from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from aya_afi.poster import image_host
from aya_afi.poster.errors import PosterAPIError, PosterValidationError


def _install_mock(
    monkeypatch: pytest.MonkeyPatch, responses: list[httpx.Response]
) -> list[httpx.Request]:
    captured: list[httpx.Request] = []
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return next(iterator)

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)
    return captured


async def test_missing_file_raises_validation(tmp_path: Path) -> None:
    with pytest.raises(PosterValidationError, match="見つかりません"):
        await image_host.upload_image(str(tmp_path / "nope.jpg"))


async def test_oversize_file_raises_validation(tmp_path: Path) -> None:
    big = tmp_path / "big.jpg"
    big.write_bytes(b"\x00" * (9 * 1024 * 1024))  # > 8 MB
    with pytest.raises(PosterValidationError, match="大きすぎます"):
        await image_host.upload_image(str(big))


async def test_successful_upload_returns_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0FAKE")

    captured = _install_mock(
        monkeypatch,
        [httpx.Response(200, text="https://files.catbox.moe/abc123.jpg")],
    )

    url = await image_host.upload_image(str(img))
    assert url == "https://files.catbox.moe/abc123.jpg"
    assert len(captured) == 1
    assert "catbox.moe" in str(captured[0].url)


async def test_non_url_response_falls_back_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")

    # Both providers return a non-URL — all-hosts-failed error.
    _install_mock(
        monkeypatch,
        [
            httpx.Response(200, text="ERROR: catbox rejected"),
            httpx.Response(200, text="ERROR: 0x0 rejected"),
        ],
    )

    with pytest.raises(PosterAPIError, match="全画像ホスト失敗"):
        await image_host.upload_image(str(img))


async def test_http_error_falls_back_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")

    _install_mock(
        monkeypatch,
        [
            httpx.Response(503, text="catbox down"),
            httpx.Response(503, text="0x0 down"),
        ],
    )

    with pytest.raises(PosterAPIError, match="全画像ホスト失敗"):
        await image_host.upload_image(str(img))


async def test_catbox_down_falls_back_to_nullpointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")

    captured = _install_mock(
        monkeypatch,
        [
            # Primary (catbox) returns the current real-world failure shape.
            httpx.Response(412, text="Uploads paused until storage resolved"),
            # Fallback (0x0.st) succeeds.
            httpx.Response(200, text="https://0x0.st/abc.jpg\n"),
        ],
    )

    url = await image_host.upload_image(str(img))
    assert url == "https://0x0.st/abc.jpg"
    assert len(captured) == 2
    assert "catbox.moe" in str(captured[0].url)
    assert "0x0.st" in str(captured[1].url)
