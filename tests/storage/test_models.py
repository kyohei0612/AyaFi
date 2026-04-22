from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from aya_afi.storage.db import init_schema, make_engine, make_session_factory
from aya_afi.storage.models import Draft, Post, PostTarget


@pytest.fixture
def session(tmp_path) -> Generator[Session, None, None]:
    engine = make_engine(tmp_path / "test.sqlite")
    init_schema(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_init_schema_creates_all_tables(tmp_path) -> None:
    engine = make_engine(tmp_path / "schema.sqlite")
    init_schema(engine)
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    assert {"posts", "post_targets", "drafts"} <= names


def test_post_gets_default_id_and_timestamps(session: Session) -> None:
    post = Post(generated_text_markdown="hi")
    session.add(post)
    session.flush()
    assert post.id is not None
    assert post.created_at is not None
    assert post.updated_at is not None
    assert post.status == "draft"
    assert post.image_paths == []
    assert post.pulldown_options == {}


def test_post_targets_cascade_on_delete(session: Session) -> None:
    post = Post()
    session.add(post)
    session.flush()
    t1 = PostTarget(post_id=post.id, sns="threads")
    t2 = PostTarget(post_id=post.id, sns="bluesky")
    session.add_all([t1, t2])
    session.commit()
    session.delete(post)
    session.commit()
    remaining = session.query(PostTarget).count()
    assert remaining == 0


def test_post_targets_unique_per_sns(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    post = Post()
    session.add(post)
    session.flush()
    session.add(PostTarget(post_id=post.id, sns="threads"))
    session.flush()
    session.add(PostTarget(post_id=post.id, sns="threads"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_draft_requires_expires_at(session: Session) -> None:
    # expires_at is non-nullable; must pass it explicitly.
    from datetime import UTC, datetime, timedelta

    draft = Draft(
        content_markdown="hello",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(draft)
    session.flush()
    assert draft.id is not None
    assert draft.post_id is None


def test_post_json_fields_roundtrip(session: Session) -> None:
    post = Post(
        image_paths=["/tmp/a.jpg", "/tmp/b.jpg"],
        pulldown_options={"hook": "story", "tone": "casual"},
    )
    session.add(post)
    session.commit()
    reread = session.get(Post, post.id)
    assert reread is not None
    assert reread.image_paths == ["/tmp/a.jpg", "/tmp/b.jpg"]
    assert reread.pulldown_options == {"hook": "story", "tone": "casual"}
