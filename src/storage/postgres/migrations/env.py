"""Alembic entry point. Runs migrations against the engine defined in storage.postgres."""

from alembic import context

from storage.postgres import (
    Base,
    engine,
    models,  # noqa: F401  imported so its tables register on Base
)

target_metadata = Base.metadata

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
