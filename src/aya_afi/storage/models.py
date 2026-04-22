"""SQLAlchemy ORM models for aya-afi persistence.

Schema derived from ADR-005. JSON columns use SQLite's TEXT (SQLAlchemy's
``JSON`` type serializes to/from dict automatically).

Status enums are kept as plain strings so we can add new states without a
schema migration; the state machine lives in ``storage.service`` /
``storage.recovery``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared declarative base for all aya-afi tables."""


# ---------------------------------------------------------------------------
# posts — one row per "I want to publish this content to some set of SNS".
# ---------------------------------------------------------------------------


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    product_url: Mapped[str | None] = mapped_column(String, nullable=True)
    product_title: Mapped[str | None] = mapped_column(String, nullable=True)
    affiliate_link: Mapped[str | None] = mapped_column(String, nullable=True)

    generated_text_markdown: Mapped[str] = mapped_column(String, default="")
    final_text_markdown: Mapped[str] = mapped_column(String, default="")

    image_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    pulldown_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String, default="draft")
    # draft / queued / posting / posted / partial / failed

    dry_run: Mapped[bool] = mapped_column(Integer, default=0)
    post_mode: Mapped[str] = mapped_column(String, default="affiliate")
    # preparation / affiliate (from ADR-012)

    targets: Mapped[list[PostTarget]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ---------------------------------------------------------------------------
# post_targets — one row per (post, sns). The ``id`` doubles as the
# idempotency key we pass to SNS APIs that support client_token (ADR-005).
# ---------------------------------------------------------------------------


class PostTarget(Base):
    __tablename__ = "post_targets"
    __table_args__ = (UniqueConstraint("post_id", "sns", name="uq_post_sns"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    post_id: Mapped[str] = mapped_column(
        String, ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    sns: Mapped[str] = mapped_column(String)  # threads / bluesky / note

    status: Mapped[str] = mapped_column(String, default="pending")
    # pending / posting / posted / failed

    attempted_count: Mapped[int] = mapped_column(Integer, default=0)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sns_post_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sns_post_url: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    post: Mapped[Post] = relationship(back_populates="targets")


# ---------------------------------------------------------------------------
# drafts — auto-saved LLM output. Survives SNS API failures (ADR-005 §drafts).
# ---------------------------------------------------------------------------


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    post_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    content_markdown: Mapped[str] = mapped_column(String)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 90-day retention by default; caller sets via service function.
