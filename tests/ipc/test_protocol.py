from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from aya_afi.ipc.protocol import (
    SCHEMA_VERSION,
    UNKNOWN_REQUEST_ID,
    ErrorInfo,
    Event,
    EventType,
    Request,
    RequestAction,
    Response,
)


def test_request_roundtrip() -> None:
    req = Request(
        request_id="abc-123",
        action=RequestAction.ping,
        params={"foo": "bar"},
    )
    raw = req.model_dump_json()
    reparsed = Request.model_validate_json(raw)
    assert reparsed == req
    assert reparsed.schema_version == SCHEMA_VERSION


def test_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Request.model_validate_json(
            json.dumps({"request_id": "x", "action": "ping", "extra_garbage": 123})
        )


def test_request_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        Request.model_validate_json(json.dumps({"request_id": "x", "action": "nonexistent"}))


def test_request_requires_request_id() -> None:
    with pytest.raises(ValidationError):
        Request.model_validate_json(json.dumps({"action": "ping"}))


def test_request_timeout_lower_bound() -> None:
    with pytest.raises(ValidationError):
        Request.model_validate_json(
            json.dumps({"request_id": "x", "action": "ping", "timeout_sec": 0})
        )


def test_request_timeout_upper_bound() -> None:
    with pytest.raises(ValidationError):
        Request.model_validate_json(
            json.dumps({"request_id": "x", "action": "ping", "timeout_sec": 3600})
        )


def test_response_ok_excludes_none_error() -> None:
    resp = Response(request_id="x", ok=True, data={"result": 42})
    parsed = json.loads(resp.model_dump_json(exclude_none=True))
    assert parsed["ok"] is True
    assert parsed["data"] == {"result": 42}
    assert "error" not in parsed


def test_response_error_payload() -> None:
    resp = Response(
        request_id="x",
        ok=False,
        error=ErrorInfo(type="rate_limit", message="too many", retry_after_sec=5.0),
    )
    parsed = json.loads(resp.model_dump_json(exclude_none=True))
    assert parsed["ok"] is False
    assert parsed["error"]["type"] == "rate_limit"
    assert parsed["error"]["retry_after_sec"] == 5.0


def test_event_heartbeat_roundtrip() -> None:
    ev = Event(event_type=EventType.heartbeat)
    assert ev.event_type.value == "heartbeat"
    reparsed = Event.model_validate_json(ev.model_dump_json())
    assert reparsed == ev


def test_sentinel_request_id_is_uuid_shape() -> None:
    # Used by server on parse failure; must be parseable by TS Zod as a UUID.
    assert UNKNOWN_REQUEST_ID.count("-") == 4
    assert len(UNKNOWN_REQUEST_ID) == 36
