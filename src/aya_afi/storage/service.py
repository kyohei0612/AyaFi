"""High-level storage operations.

Implements the pieces of ADR-005 we need for Stage 5.a: create drafts, record
post + targets atomically (write-first), update target results, find recent
duplicates (Layer 1 dedupe), list drafts, cleanup expired drafts.

Full state-machine-with-retry orchestration lives in Stage 3.b (wired to the
Poster layer). For now this module provides the data-plane primitives.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from aya_afi.storage.models import Draft, Post, PostTarget

DEFAULT_DUPLICATE_WINDOW_MIN = 5
DEFAULT_DRAFT_RETENTION_DAYS = 90


def create_post_with_targets(
    session: Session,
    *,
    sns_list: Iterable[str],
    product_url: str | None = None,
    product_title: str | None = None,
    affiliate_link: str | None = None,
    generated_text: str = "",
    final_text: str = "",
    image_paths: list[str] | None = None,
    pulldown_options: dict[str, Any] | None = None,
    post_mode: str = "affiliate",
    dry_run: bool = False,
) -> Post:
    """Write-first: insert Post + all PostTarget rows in a single transaction.

    Initial statuses: ``posts.status='queued'``, ``post_targets.status='pending'``.
    Returns the attached ``Post`` instance (caller should commit).
    """
    post = Post(
        product_url=product_url,
        product_title=product_title,
        affiliate_link=affiliate_link,
        generated_text_markdown=generated_text,
        final_text_markdown=final_text or generated_text,
        image_paths=list(image_paths or []),
        pulldown_options=dict(pulldown_options or {}),
        status="queued",
        dry_run=bool(dry_run),
        post_mode=post_mode,
    )
    session.add(post)
    session.flush()  # assigns post.id
    for sns in sns_list:
        target = PostTarget(post_id=post.id, sns=sns, status="pending")
        session.add(target)
    session.flush()
    return post


def mark_post_posting(session: Session, post_id: str) -> Post:
    post = session.get(Post, post_id)
    if post is None:
        raise LookupError(f"post not found: {post_id}")
    post.status = "posting"
    session.flush()
    return post


def record_target_success(
    session: Session,
    *,
    target_id: str,
    sns_post_id: str | None,
    sns_post_url: str | None,
) -> PostTarget:
    """Mark a PostTarget as posted (success path)."""
    target = session.get(PostTarget, target_id)
    if target is None:
        raise LookupError(f"post_target not found: {target_id}")
    target.status = "posted"
    target.sns_post_id = sns_post_id
    target.sns_post_url = sns_post_url
    target.posted_at = datetime.now(UTC)
    target.last_error_type = None
    target.last_error_message = None
    session.flush()
    return target


def record_target_failure(
    session: Session,
    *,
    target_id: str,
    error_type: str,
    error_message: str,
) -> PostTarget:
    """Mark a PostTarget as failed (transient or permanent — caller decides retry)."""
    target = session.get(PostTarget, target_id)
    if target is None:
        raise LookupError(f"post_target not found: {target_id}")
    target.status = "failed"
    target.last_error_type = error_type
    target.last_error_message = error_message
    session.flush()
    return target


def aggregate_post_status(session: Session, post_id: str) -> str:
    """Compute post.status from its children and persist it.

    Rules:
    - All targets posted → ``posted``
    - All targets failed → ``failed``
    - Mix of posted + failed → ``partial``
    - Any target still pending/posting → ``posting`` (keep as-is)
    """
    post = session.get(Post, post_id)
    if post is None:
        raise LookupError(f"post not found: {post_id}")
    targets = post.targets
    if not targets:
        post.status = "failed"
    else:
        statuses = {t.status for t in targets}
        if statuses <= {"posted"}:
            post.status = "posted"
        elif statuses <= {"failed"}:
            post.status = "failed"
        elif "pending" in statuses or "posting" in statuses:
            post.status = "posting"
        else:
            # Mix of posted + failed (no pending/posting left).
            post.status = "partial"
    session.flush()
    return post.status


def find_recent_duplicates(
    session: Session,
    *,
    product_url: str,
    window_min: int = DEFAULT_DUPLICATE_WINDOW_MIN,
) -> list[Post]:
    """ADR-005 Layer 1 dedupe. Returns non-empty list if a matching Post was
    queued/posting/posted/partial within ``window_min`` minutes."""
    if not product_url:
        return []
    since = datetime.now(UTC) - timedelta(minutes=window_min)
    stmt = select(Post).where(
        and_(
            Post.product_url == product_url,
            Post.created_at >= since,
            Post.status.in_(("queued", "posting", "posted", "partial")),
        )
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


def save_draft(
    session: Session,
    *,
    content_markdown: str,
    post_id: str | None = None,
    file_path: str | None = None,
    retention_days: int = DEFAULT_DRAFT_RETENTION_DAYS,
) -> Draft:
    draft = Draft(
        post_id=post_id,
        content_markdown=content_markdown,
        file_path=file_path,
        expires_at=datetime.now(UTC) + timedelta(days=retention_days),
    )
    session.add(draft)
    session.flush()
    return draft


def list_drafts(session: Session, *, limit: int = 50, include_expired: bool = False) -> list[Draft]:
    stmt = select(Draft).order_by(Draft.created_at.desc()).limit(limit)
    if not include_expired:
        stmt = stmt.where(Draft.expires_at >= datetime.now(UTC))
    return list(session.scalars(stmt).all())


def cleanup_expired_drafts(session: Session) -> int:
    """Delete drafts past their ``expires_at``. Returns count deleted."""
    stmt = select(Draft).where(Draft.expires_at < datetime.now(UTC))
    expired = list(session.scalars(stmt).all())
    for d in expired:
        session.delete(d)
    session.flush()
    return len(expired)
