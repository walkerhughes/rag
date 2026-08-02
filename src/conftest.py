"""Shared test fixtures. The database fixtures are requested only by integration tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from storage.postgres import Base, engine

REPO_ROOT = Path(__file__).parents[1]

# Children before parents, so foreign keys stay satisfied while clearing.
CORPUS_TABLES = (
    "transcript_segment",
    "episode_speaker",
    "episode",
    "speaker",
    "ingestion_run",
)


def clear_corpus() -> None:
    with Session(engine) as cleanup:
        for table in CORPUS_TABLES:
            cleanup.execute(Base.metadata.tables[table].delete())
        cleanup.commit()


@pytest.fixture
def session() -> Iterator[Session]:
    """An empty corpus before and after.

    Clearing beforehand matters because a real ingestion run, or a previous test, may have
    left rows behind. Migrating each time matters because the migration tests leave the
    database at base.
    """
    command.upgrade(Config(str(REPO_ROOT / "alembic.ini")), "head")
    clear_corpus()
    with Session(engine) as active:
        yield active
        active.rollback()
    clear_corpus()
