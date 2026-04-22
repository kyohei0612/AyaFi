from __future__ import annotations

import json

import pytest

from aya_afi.config.settings import Settings
from aya_afi.ipc.handlers import make_fetch_product_handler
from aya_afi.ipc.protocol import FetchProductResult, Request, RequestAction
from aya_afi.ipc.server import IpcServer


class Sink:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, line: str) -> None:
        self.lines.append(line)


@pytest.fixture
def sink() -> Sink:
    return Sink()


@pytest.fixture
def force_mock_settings() -> Settings:
    # Bypass real HTTP by forcing the mock provider regardless of URL.
    return Settings(
        _env_file=None,
        llm_provider="mock",
        affiliate_force_mock=True,
    )


@pytest.fixture
def server_with_fetch_handler(sink: Sink, force_mock_settings: Settings) -> IpcServer:
    srv = IpcServer(writer=sink)
    srv.register(
        RequestAction.fetch_product,
        make_fetch_product_handler(force_mock_settings),
    )
    return srv


async def test_fetch_product_returns_mock_info(
    server_with_fetch_handler: IpcServer, sink: Sink
) -> None:
    req = Request(
        request_id="f1",
        action=RequestAction.fetch_product,
        params={"url": "https://item.rakuten.co.jp/a/b/"},
    )
    await server_with_fetch_handler.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is True
    result = FetchProductResult.model_validate(resp["data"])
    assert result.url == "https://item.rakuten.co.jp/a/b/"
    assert result.title.startswith("[MOCK PRODUCT]")
    assert result.price_yen == 1980


async def test_fetch_product_missing_url_is_validation_error(
    server_with_fetch_handler: IpcServer, sink: Sink
) -> None:
    req = Request(
        request_id="f2",
        action=RequestAction.fetch_product,
        params={},
    )
    await server_with_fetch_handler.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is False
    assert resp["error"]["type"] == "validation"


async def test_fetch_product_extra_params_rejected(
    server_with_fetch_handler: IpcServer, sink: Sink
) -> None:
    req = Request(
        request_id="f3",
        action=RequestAction.fetch_product,
        params={"url": "https://x", "unknown": 1},
    )
    await server_with_fetch_handler.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is False
    assert resp["error"]["type"] == "validation"


async def test_fetch_product_unknown_url_when_not_forced_mock(sink: Sink) -> None:
    # Without force_mock, unknown URLs route to the unsupported_url error.
    settings = Settings(_env_file=None, llm_provider="mock")
    srv = IpcServer(writer=sink)
    srv.register(RequestAction.fetch_product, make_fetch_product_handler(settings))
    req = Request(
        request_id="f4",
        action=RequestAction.fetch_product,
        params={"url": "https://yahoo.co.jp/x"},
    )
    await srv.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is False
    assert resp["error"]["type"] == "unsupported_url"
