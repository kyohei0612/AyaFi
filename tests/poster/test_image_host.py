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


async def test_non_url_response_is_api_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")

    _install_mock(monkeypatch, [httpx.Response(200, text="ERROR: too big")])

    with pytest.raises(PosterAPIError, match="unexpected payload"):
        await image_host.upload_image(str(img))


async def test_http_error_is_api_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")

    _install_mock(monkeypatch, [httpx.Response(503, text="catbox down")])

    with pytest.raises(PosterAPIError, match="503"):
        await image_host.upload_image(str(img))
