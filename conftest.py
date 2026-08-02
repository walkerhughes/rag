"""Shared test fixtures for both src and apps."""

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from corpus.ingestion.dwarkesh import client
from storage.postgres import Base, engine

REPO_ROOT = Path(__file__).parent
FIXTURES = REPO_ROOT / "src/corpus/ingestion/dwarkesh/fixtures"

# Children before parents, so foreign keys stay satisfied while clearing.
CORPUS_TABLES = (
    "transcript_segment",
    "episode_speaker",
    "episode",
    "speaker",
    "ingestion_run",
)


def alembic_config() -> Config:
    return Config(str(REPO_ROOT / "alembic.ini"))


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
    command.upgrade(alembic_config(), "head")
    clear_corpus()
    with Session(engine) as active:
        yield active
        active.rollback()
    clear_corpus()


@pytest.fixture
def listing() -> Callable[..., client.EpisodeListing]:
    def build(slug: str = "richard-sutton") -> client.EpisodeListing:
        return client.EpisodeListing(
            slug=slug,
            title="Richard Sutton",
            canonical_url=f"https://www.dwarkesh.com/p/{slug}",
            post_date=date(2025, 9, 26),
            type="podcast",
        )

    return build


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serves the committed fixture for known slugs and fails for anything else."""

    def fetch_page(slug: str) -> str:
        path = FIXTURES / f"{slug}.html"
        if not path.exists():
            raise client.FetchError(f"{slug}: not found")
        return path.read_text()

    monkeypatch.setattr(client, "fetch_page", fetch_page)
