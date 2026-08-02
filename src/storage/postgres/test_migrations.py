"""Migration tests. These need the docker-compose database, so they are integration tests."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from storage.postgres import engine

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).parents[3]


@pytest.fixture
def alembic_config() -> Config:
    """An empty database, so every test starts from the same place."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    return Config(str(REPO_ROOT / "alembic.ini"))


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


def test_empty_database_reaches_head(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    assert current_revision() == ScriptDirectory.from_config(alembic_config).get_current_head()


def test_schema_at_head_matches_the_models(alembic_config: Config) -> None:
    """Fails when a model changes without a migration, or a migration drifts from the models."""
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)


def test_pgvector_is_available(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        installed = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert installed == 1


def test_downgrade_to_base_leaves_no_application_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    with engine.connect() as connection:
        tables = connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        ).scalars()
        assert list(tables) == []
