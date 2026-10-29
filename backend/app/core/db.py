"""SQLAlchemy engine + session handling.

Several processes share the SQLite file (API/agents/scheduler + one process per MCP server), so:
* WAL journal + busy timeout let readers and a writer coexist;
* sessions are short-lived (`session_scope`) and committed before any MCP call — the same
  "one implicit transaction per call" semantics Prisma had — so no process holds the write lock
  while waiting on another.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=15000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        url = get_settings().database_url
        _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15} if url.startswith("sqlite") else {})
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _configure_sqlite)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Tests switch DATABASE_URL between runs."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _factory is not None
    s = _factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    """Bring the schema to the latest Alembic revision. Databases created before migrations existed
    (tables but no `alembic_version`) are stamped at the baseline first, then upgraded."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from app import models  # noqa: F401  (registers tables)

    engine = get_engine()
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    tables = set(inspect(engine).get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")
