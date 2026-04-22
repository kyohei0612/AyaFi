"""Engine + session factory + schema bootstrap.

For v0.1 we create tables via ``Base.metadata.create_all`` at startup; alembic
proper lands when the schema needs to evolve in v0.2 (ADR-005 §Rollback).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from aya_afi.storage.models import Base
from aya_afi.utils.paths import get_db_path


def make_engine(db_path: Path | None = None) -> Engine:
    """Build a SQLite engine pointed at ``db_path`` (or the default user dir)."""
    path = db_path if db_path is not None else get_db_path()
    # SQLite needs this for multi-threaded access; we're single-writer but
    # reads may happen from other threads (e.g. IPC dispatcher + recovery).
    url = f"sqlite:///{path}"
    engine = create_engine(url, future=True)
    return engine


def init_schema(engine: Engine) -> None:
    """Create all aya-afi tables if they do not exist yet."""
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
