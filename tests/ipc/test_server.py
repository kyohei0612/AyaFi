from __future__ import annotations

import asyncio
import json

import pytest

from aya_afi.ipc.protocol import Request, RequestAction, Response
from aya_afi.ipc.server import IpcServer


class Sink:
    """Captures lines emitted by the server for assertion."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, line: str) -> None:
        self.lines.append(line)

    def last_response(self) -> Response:
        for line in reversed(self.lines):
            payload = json.loads(line)
            if "ok" in payload:
                return Response.model_validate(payload)
        raise AssertionError("no Response emitted")


@pytest.fixture
def sink() -> Sink:
    return Sink()


@pytest.fixture
def server(sink: Sink) -> IpcServer:
    srv = IpcServer(writer=sink)

    async def pong(req: Request) -> dict[str, object]:
        return {"echo": req.params.get("message")}

    async def slow(_req: Request) -> dict[str, object]:
        await asyncio.sleep(10)
        return {}

    async def boom(_req: Request) -> dict[str, object]:
        raise RuntimeError("kaboom")

    srv.register(RequestAction.ping, pong)
    srv.register(RequestAction.health_check, slow)
    srv.register(RequestAction.generate_post, boom)
    return srv


async def test_ping_handler_returns_pong(server: IpcServer, sink: Sink) -> None:
    req = Request(
        request_id="r1",
        action=RequestAction.ping,
        params={"message": "hi"},
    )
    await server.handle_line(req.model_dump_json())
    resp = sink.last_response()
    assert resp.ok is True
    assert resp.data == {"echo": "hi"}
    assert resp.request_id == "r1"


async def test_unknown_action_returns_error(server: IpcServer, sink: Sink) -> None:
    raw = json.dumps({"request_id": "r2", "action": "publish"})
    await server.handle_line(raw)
    resp = sink.last_response()
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.type == "unknown_action"
    assert resp.request_id == "r2"


async def test_parse_error_uses_sentinel_id(server: IpcServer, sink: Sink) -> None:
    await server.handle_line('{"request_id": "x", "action": 42}')  # action wrong type
    resp = sink.last_response()
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.type == "parse"
    assert resp.request_id.startswith("00000000")


async def test_empty_line_emits_nothing(server: IpcServer, sink: Sink) -> None:
    await server.handle_line("")
    await server.handle_line("   \n")
    assert sink.lines == []


async def test_timeout_emitted(server: IpcServer, sink: Sink) -> None:
    req = Request(
        request_id="r3",
        action=RequestAction.health_check,  # fixture's slow handler
        timeout_sec=0.05,
    )
    await server.handle_line(req.model_dump_json())
    resp = sink.last_response()
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.type == "timeout"


async def test_handler_exception_captured(server: IpcServer, sink: Sink) -> None:
    req = Request(
        request_id="r4",
        action=RequestAction.generate_post,  # fixture's boom handler
    )
    await server.handle_line(req.model_dump_json())
    resp = sink.last_response()
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.type == "internal"
    assert "kaboom" in resp.error.message


async def test_extra_fields_rejected(server: IpcServer, sink: Sink) -> None:
    raw = json.dumps({"request_id": "r5", "action": "ping", "unknown_field": "bad"})
    await server.handle_line(raw)
    resp = sink.last_response()
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.type == "parse"
