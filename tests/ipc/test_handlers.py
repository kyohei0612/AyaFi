from __future__ import annotations

import json

import pytest

from aya_afi.ipc.handlers import make_generate_post_handler
from aya_afi.ipc.protocol import GeneratePostResult, Request, RequestAction
from aya_afi.ipc.server import IpcServer
from aya_afi.llm.mock import MockLLMProvider


class Sink:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, line: str) -> None:
        self.lines.append(line)


@pytest.fixture
def sink() -> Sink:
    return Sink()


@pytest.fixture
def server_with_mock_llm(sink: Sink) -> IpcServer:
    srv = IpcServer(writer=sink)
    llm = MockLLMProvider(canned_response="generated post text")
    srv.register(RequestAction.generate_post, make_generate_post_handler(llm))
    return srv


async def test_generate_post_returns_llm_text(server_with_mock_llm: IpcServer, sink: Sink) -> None:
    req = Request(
        request_id="g1",
        action=RequestAction.generate_post,
        params={"user_prompt": "商品 X を紹介して"},
    )
    await server_with_mock_llm.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is True
    result = GeneratePostResult.model_validate(resp["data"])
    assert result.text == "generated post text"
    assert result.provider == "mock"


async def test_generate_post_missing_user_prompt_errors(
    server_with_mock_llm: IpcServer, sink: Sink
) -> None:
    req = Request(
        request_id="g2",
        action=RequestAction.generate_post,
        params={},
    )
    await server_with_mock_llm.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is False
    assert resp["error"]["type"] == "validation"


async def test_generate_post_rejects_extra_params(
    server_with_mock_llm: IpcServer, sink: Sink
) -> None:
    req = Request(
        request_id="g3",
        action=RequestAction.generate_post,
        params={"user_prompt": "hi", "stray_field": 1},
    )
    await server_with_mock_llm.handle_line(req.model_dump_json())
    resp = json.loads(sink.lines[-1])
    assert resp["ok"] is False
    assert resp["error"]["type"] == "validation"
