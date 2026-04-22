"""Poster layer types + Protocol.

Each concrete poster (``threads``, ``bluesky``, ``note``, ``mock``) implements
``Poster``. ADR-005 / ADR-012 design notes embedded as docstrings so
implementers don't have to cross-reference.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from aya_afi.sns_engine.base import SnsKind

SCHEMA_VERSION = 1


class PostRequest(BaseModel):
    """Input to a ``Poster.publish`` call.

    Fields map to ADR-005 ``post_targets`` row: ``idempotency_key`` is the
    ``post_target.id`` so the SNS API (when it supports client_token) can
    dedupe retries server-side.

    Threads-specific:
    - ``body`` goes to the parent post.
    - ``reply_body`` is posted as a self-reply holding the affiliate link
      (ADR-012 §2 — required to avoid the initial-15-min penalty).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    sns: SnsKind
    body: str = Field(..., min_length=1)
    reply_body: str | None = Field(
        default=None,
        description="For Threads 2-step posting: affiliate URL + optional context.",
    )
    image_paths: list[str] = Field(
        default_factory=list,
        description="Absolute paths to local image files. Poster uploads them.",
    )
    idempotency_key: str = Field(
        ...,
        min_length=1,
        description=(
            "Stable UUID from post_targets.id (ADR-005). Used as client_token "
            "where supported to dedupe retries."
        ),
    )
    dry_run: bool = Field(
        default=False,
        description="If True, Poster logs what would happen and returns success "
        "without touching any SNS API.",
    )


class PostResult(BaseModel):
    """Outcome of a single publish call."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    success: bool
    sns: SnsKind
    sns_post_id: str | None = None
    sns_post_url: str | None = None
    reply_post_id: str | None = Field(
        default=None,
        description="Threads 2-step: id of the reply that carries the affiliate link.",
    )
    error_type: str | None = None
    error_message: str | None = None


@runtime_checkable
class Poster(Protocol):
    """All concrete posters must satisfy this shape."""

    name: str

    async def publish(self, req: PostRequest) -> PostResult: ...
