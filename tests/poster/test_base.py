from __future__ import annotations

import pytest
from pydantic import ValidationError

from aya_afi.poster.base import Poster, PostRequest, PostResult
from aya_afi.poster.mock import MockPoster
from aya_afi.sns_engine.base import SnsKind


def _req(**overrides: object) -> PostRequest:
    defaults: dict[str, object] = {
        "sns": SnsKind.threads,
        "body": "Hello world",
        "idempotency_key": "test-key-1",
    }
    defaults.update(overrides)
    return PostRequest.model_validate(defaults)


def test_request_roundtrip() -> None:
    req = _req(reply_body="with URL", image_paths=["/tmp/a.jpg"])
    parsed = PostRequest.model_validate_json(req.model_dump_json())
    assert parsed == req


def test_request_rejects_empty_body() -> None:
    with pytest.raises(ValidationError):
        PostRequest.model_validate({"sns": "threads", "body": "", "idempotency_key": "k"})


def test_request_rejects_empty_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        PostRequest.model_validate({"sns": "threads", "body": "hi", "idempotency_key": ""})


def test_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PostRequest.model_validate(
            {
                "sns": "threads",
                "body": "hi",
                "idempotency_key": "k",
                "unknown": 1,
            }
        )


def test_mock_satisfies_protocol() -> None:
    provider = MockPoster()
    assert isinstance(provider, Poster)
    assert provider.name == "mock"


def test_result_without_sns_post_id_allowed() -> None:
    # Partial success (e.g. dry-run with no real id) is representable.
    result = PostResult(success=True, sns=SnsKind.note)
    assert result.sns_post_id is None
