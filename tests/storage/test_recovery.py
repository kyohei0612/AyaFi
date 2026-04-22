from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from aya_afi.storage.db import init_schema, make_engine, make_session_factory
from aya_afi.storage.recovery import scan_orphans
from aya_afi.storage.service import create_post_with_targets


@pytest.fixture
def session(tmp_path) -> Generator[Session, None, None]:
    engine = make_engine(tmp_path / "test.sqlite")
    init_schema(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_scan_orphans_finds_stale_posting(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads", "bluesky"])
    post.status = "posting"
    for t in post.targets:
        t.status = "posting"
    # Fake an old updated_at
    post.updated_at = datetime.now(UTC) - timedelta(hours=2)
    session.commit()

    orphans = scan_orphans(session, stale_after_min=30)
    assert len(orphans) == 1
    assert orphans[0].post.id == post.id
    assert len(orphans[0].orphan_targets) == 2


def test_scan_orphans_ignores_fresh_posting(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads"])
    post.status = "posting"
    # updated_at defaults to now — not stale
    session.commit()

    orphans = scan_orphans(session, stale_after_min=30)
    assert orphans == []


def test_scan_orphans_ignores_terminal_statuses(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads"])
    post.status = "posted"
    post.updated_at = datetime.now(UTC) - timedelta(hours=5)
    session.commit()

    orphans = scan_orphans(session, stale_after_min=30)
    assert orphans == []
