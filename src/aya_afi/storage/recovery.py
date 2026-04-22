"""Startup recovery: find posts left in mid-publish state from a previous run.

Called once on sidecar start (Stage 5.b wiring). Never auto-retries — a post
stuck in ``posting`` might have actually succeeded server-side, and the
ADR-005 design says the wife verifies manually before deciding.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from aya_afi.storage.models import Post, PostTarget


class OrphanPost(NamedTuple):
    post: Post
    orphan_targets: list[PostTarget]


def scan_orphans(session: Session, *, stale_after_min: int = 30) -> list[OrphanPost]:
    """Return posts stuck in ``queued`` / ``posting`` longer than ``stale_after_min``.

    Pairs each with its targets in pending/posting states so the UI can show
    "これ投稿成功してる? Threads で確認して" per target.
    """
    threshold = datetime.now(UTC) - timedelta(minutes=stale_after_min)
    stmt = (
        select(Post)
        .where(Post.status.in_(("queued", "posting")))
        .where(Post.updated_at < threshold)
        .order_by(Post.updated_at.asc())
    )
    orphans: list[OrphanPost] = []
    for post in session.scalars(stmt).all():
        stuck = [t for t in post.targets if t.status in ("pending", "posting")]
        orphans.append(OrphanPost(post=post, orphan_targets=stuck))
    return orphans
