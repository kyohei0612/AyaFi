from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from aya_afi.storage.db import init_schema, make_engine, make_session_factory
from aya_afi.storage.models import Draft
from aya_afi.storage.service import (
    aggregate_post_status,
    cleanup_expired_drafts,
    create_post_with_targets,
    find_recent_duplicates,
    list_drafts,
    mark_post_posting,
    record_target_failure,
    record_target_success,
    save_draft,
)


@pytest.fixture
def session(tmp_path) -> Generator[Session, None, None]:
    engine = make_engine(tmp_path / "test.sqlite")
    init_schema(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_create_post_with_targets_writes_all_rows(session: Session) -> None:
    post = create_post_with_targets(
        session,
        sns_list=["threads", "bluesky", "note"],
        product_url="https://item.rakuten.co.jp/s/i/",
        product_title="電気ケトル",
        affiliate_link="https://hb.afl.rakuten.co.jp/x",
        generated_text="生成文",
        image_paths=["/tmp/a.jpg"],
        pulldown_options={"hook": "story"},
        post_mode="affiliate",
    )
    session.commit()

    assert post.status == "queued"
    assert post.final_text_markdown == "生成文"  # defaults to generated
    assert len(post.targets) == 3
    for t in post.targets:
        assert t.status == "pending"
        assert t.attempted_count == 0


def test_mark_post_posting_transitions(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads"])
    session.commit()
    updated = mark_post_posting(session, post.id)
    assert updated.status == "posting"


def test_record_target_success_fills_fields(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads"])
    target_id = post.targets[0].id
    session.commit()

    target = record_target_success(
        session,
        target_id=target_id,
        sns_post_id="t-123",
        sns_post_url="https://threads.net/@u/post/t-123",
    )
    assert target.status == "posted"
    assert target.sns_post_id == "t-123"
    assert target.posted_at is not None


def test_record_target_failure_keeps_message(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads"])
    target_id = post.targets[0].id
    session.commit()
    target = record_target_failure(
        session,
        target_id=target_id,
        error_type="rate_limit",
        error_message="throttled",
    )
    assert target.status == "failed"
    assert target.last_error_type == "rate_limit"


def test_aggregate_all_posted(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads", "bluesky"])
    for t in post.targets:
        record_target_success(session, target_id=t.id, sns_post_id="x", sns_post_url="https://x")
    session.commit()
    assert aggregate_post_status(session, post.id) == "posted"


def test_aggregate_partial(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads", "bluesky"])
    record_target_success(
        session,
        target_id=post.targets[0].id,
        sns_post_id="x",
        sns_post_url="https://x",
    )
    record_target_failure(
        session,
        target_id=post.targets[1].id,
        error_type="api_down",
        error_message="5xx",
    )
    session.commit()
    assert aggregate_post_status(session, post.id) == "partial"


def test_aggregate_all_failed(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads"])
    record_target_failure(
        session,
        target_id=post.targets[0].id,
        error_type="api_down",
        error_message="5xx",
    )
    session.commit()
    assert aggregate_post_status(session, post.id) == "failed"


def test_aggregate_still_pending(session: Session) -> None:
    post = create_post_with_targets(session, sns_list=["threads", "bluesky"])
    record_target_success(
        session,
        target_id=post.targets[0].id,
        sns_post_id="x",
        sns_post_url="https://x",
    )
    # 2nd target still pending
    session.commit()
    assert aggregate_post_status(session, post.id) == "posting"


def test_find_recent_duplicates_hits_within_window(session: Session) -> None:
    url = "https://amazon.co.jp/dp/B00TEST"
    create_post_with_targets(session, sns_list=["threads"], product_url=url)
    session.commit()

    dupes = find_recent_duplicates(session, product_url=url, window_min=5)
    assert len(dupes) == 1


def test_find_recent_duplicates_misses_outside_window(session: Session) -> None:
    url = "https://amazon.co.jp/dp/B00OLD"
    post = create_post_with_targets(session, sns_list=["threads"], product_url=url)
    # Fake an old timestamp
    post.created_at = datetime.now(UTC) - timedelta(minutes=30)
    session.commit()

    dupes = find_recent_duplicates(session, product_url=url, window_min=5)
    assert dupes == []


def test_find_duplicates_ignores_draft_status(session: Session) -> None:
    url = "https://amazon.co.jp/dp/B00DRAFT"
    post = create_post_with_targets(session, sns_list=["threads"], product_url=url)
    post.status = "draft"
    session.commit()
    dupes = find_recent_duplicates(session, product_url=url, window_min=5)
    assert dupes == []


def test_save_and_list_drafts(session: Session) -> None:
    save_draft(session, content_markdown="first")
    save_draft(session, content_markdown="second")
    session.commit()
    drafts = list_drafts(session)
    # Newest first
    assert [d.content_markdown for d in drafts] == ["second", "first"]


def test_cleanup_expired_drafts(session: Session) -> None:
    # Fresh draft
    fresh = save_draft(session, content_markdown="new")
    # Expired draft
    expired = save_draft(session, content_markdown="old")
    expired.expires_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()

    removed = cleanup_expired_drafts(session)
    session.commit()
    assert removed == 1

    remaining = session.query(Draft).all()
    assert [d.id for d in remaining] == [fresh.id]
