"""Migration tests. These need the docker-compose database, so they are integration tests."""

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from conftest import alembic_config
from sqlalchemy import text

from storage.postgres import engine

pytestmark = pytest.mark.integration


@pytest.fixture
def empty_database(database: None) -> Config:
    """Drops and recreates the schema, so every test starts from nothing."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    return alembic_config()


def current_revision() -> str | None:
    with engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT version_num FROM alembic_version"
                " WHERE EXISTS (SELECT FROM information_schema.tables"
                " WHERE table_name = 'alembic_version')"
            )
        )
        return result.scalar_one_or_none()


def test_empty_database_reaches_head(empty_database: Config) -> None:
    command.upgrade(empty_database, "head")
    assert current_revision() == ScriptDirectory.from_config(empty_database).get_current_head()


def test_schema_at_head_matches_the_models(empty_database: Config) -> None:
    """Fails when a model changes without a migration, or a migration drifts from the models."""
    command.upgrade(empty_database, "head")
    command.check(empty_database)


def test_pgvector_is_available(empty_database: Config) -> None:
    command.upgrade(empty_database, "head")
    with engine.connect() as connection:
        installed = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert installed == 1


def test_downgrade_to_base_leaves_no_application_tables(empty_database: Config) -> None:
    command.upgrade(empty_database, "head")
    command.downgrade(empty_database, "base")
    with engine.connect() as connection:
        tables = connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        ).scalars()
        assert list(tables) == []
