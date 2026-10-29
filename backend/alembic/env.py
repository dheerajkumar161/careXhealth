"""Alembic environment: uses the application's engine/settings so CLI and `init_db()` migrate the same database."""
from __future__ import annotations

from alembic import context

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.core.db import Base, get_engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection") or get_engine()
    if hasattr(connectable, "connect") and not hasattr(connectable, "execute"):
        with connectable.connect() as conn:
            _run(conn)
    else:
        _run(connectable)


def _run(conn) -> None:  # noqa: ANN001
    context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
