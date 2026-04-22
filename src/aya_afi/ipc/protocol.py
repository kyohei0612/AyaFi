"""IPC message types. Single source of truth for Tauri ↔ Python protocol.

All messages are pydantic models; the TypeScript side is generated from these
by ``scripts/gen_ts_types.py`` (datamodel-code-generator).

See: docs/decisions/003-ipc-protocol.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

# Sentinel used for Response.request_id when the inbound Request failed to parse
# (the original id cannot be recovered). Callers on the Tauri side treat this
# as an unattributable error response.
UNKNOWN_REQUEST_ID = "00000000-0000-0000-0000-000000000000"


class RequestAction(StrEnum):
    """Actions the Python sidecar knows how to handle."""

    ping = "ping"
    health_check = "health_check"
    fetch_product = "fetch_product"
    generate_post = "generate_post"
    validate_content = "validate_content"
    publish = "publish"
    list_drafts = "list_drafts"


class Request(BaseModel):
    """Tauri → Python. Strict schema; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    request_id: str = Field(..., min_length=1, description="UUID v4")
    action: RequestAction
    params: dict[str, Any] = Field(default_factory=dict)
    timeout_sec: float = Field(default=30.0, gt=0.0, le=600.0)
    idempotency_key: str | None = Field(
        default=None,
        description="For ADR-005 publish requests; matches post_target.id.",
    )


class ErrorInfo(BaseModel):
    """Structured error payload returned on Response.ok=False."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        ...,
        description=(
            "Stable error code: parse / unknown_action / timeout / internal / "
            "rate_limit / api_down / validation / llm_quota_exceeded / ..."
        ),
    )
    message: str
    detail: str | None = None
    retry_after_sec: float | None = Field(default=None, gt=0.0)


class Response(BaseModel):
    """Python → Tauri. Correlates with a Request via request_id."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    request_id: str
    ok: bool
    data: dict[str, Any] | None = None
    error: ErrorInfo | None = None


class EventType(StrEnum):
    """Unsolicited notifications from Python to Tauri."""

    heartbeat = "heartbeat"
    sidecar_ready = "sidecar_ready"
    sidecar_error = "sidecar_error"
    progress = "progress"


class Event(BaseModel):
    """Python → Tauri; not correlated to a Request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Action-specific params / results. Used by handlers to validate ``req.params``
# and shape Response.data. Keep these near the Request/Response types so the
# TypeScript generator (ADR-003) picks them up.
# ---------------------------------------------------------------------------


class GeneratePostParams(BaseModel):
    """Params for ``RequestAction.generate_post``."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(
        default=(
            "あなたは日本語で魅力的な SNS アフィリエイト投稿文を書くアシスタントです。"
            "誇大表現を避け、実体験の捏造をしない範囲で、共感を呼ぶ文章を出力してください。"
        ),
        min_length=1,
    )
    user_prompt: str = Field(..., min_length=1)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0, le=8192)


class GeneratePostResult(BaseModel):
    """Response.data shape for ``RequestAction.generate_post``."""

    model_config = ConfigDict(extra="forbid")

    text: str
    model: str
    provider: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class FetchProductParams(BaseModel):
    """Params for ``RequestAction.fetch_product``."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1)


class FetchProductResult(BaseModel):
    """Response.data shape for ``RequestAction.fetch_product``.

    Mirrors ``affiliate.base.ProductInfo`` so the same fields flow through IPC
    unchanged. ``source`` is a string (not the enum) for TypeScript ergonomics.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    source: str
    affiliate_url: str
    title: str = ""
    price_yen: int | None = None
    description: str = ""
    image_urls: list[str] = Field(default_factory=list)
    shop_name: str | None = None
    category: str | None = None


class ValidateContentParams(BaseModel):
    """Params for ``RequestAction.validate_content``."""

    model_config = ConfigDict(extra="forbid")

    sns: str = Field(..., description="Target SNS: 'threads' (Stage 4.a), more later")
    mode: str = Field(..., description="Post mode: 'preparation' or 'affiliate'")
    body: str = Field(..., min_length=0)


class ValidationIssueDto(BaseModel):
    """Wire representation of ``sns_engine.base.ValidationIssue``."""

    model_config = ConfigDict(extra="forbid")

    severity: str
    rule_id: str
    message: str
    field: str | None = None


class ValidateContentResult(BaseModel):
    """Response.data shape for ``RequestAction.validate_content``."""

    model_config = ConfigDict(extra="forbid")

    sns: str
    mode: str
    char_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    issues: list[ValidationIssueDto] = Field(default_factory=list)
