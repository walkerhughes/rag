"""Postgres connection and session management.

`Base.metadata` is what Alembic compares the live schema against, so every persistence
model must inherit from `Base` and be imported before autogenerate runs.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


# create_engine opens no connection, so importing this module never needs a live database.
engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
SQLAlchemyInstrumentor().instrument(engine=engine)

_session_factory = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session() -> Iterator[Session]:
    """Commits when the block succeeds, rolls back when it raises."""
    with _session_factory() as active:
        try:
            yield active
            active.commit()
        except Exception:
            active.rollback()
            raise
