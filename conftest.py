"""Shared test fixtures for both src and apps."""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from opensearchpy import OpenSearch
from sqlalchemy.orm import Session

from corpus import repository
from corpus.ingestion.dwarkesh import client
from corpus.models import Episode, TranscriptSegment
from retrieval import bm25
from retrieval.indexing import index_episode, project_to_search
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


@pytest.fixture
def search_index() -> OpenSearch:
    """An empty search index, rebuilt from scratch so tests never inherit documents."""
    search = bm25.client()
    bm25.recreate_index(search)
    return search


def build_episode(
    session: Session,
    source_id: str,
    speaker: str,
    published: date,
    texts: list[str],
) -> None:
    """Stores one episode of alternating host and guest turns, and chunks it."""
    run = repository.start_run(session, "test")
    episode = Episode(
        source_id=source_id,
        title=source_id.replace("-", " ").title(),
        url=f"https://example.com/{source_id}",
        published_at=published,
        segments=[
            TranscriptSegment(
                position=index,
                speaker=speaker if index % 2 else "Dwarkesh Patel",
                text=text,
                start=timedelta(minutes=index),
            )
            for index, text in enumerate(texts)
        ],
    )
    index_episode(session, repository.save_episode(session, run, episode))


@pytest.fixture
def corpus(session: Session) -> Session:
    """Two chunked episodes, on subjects far enough apart that a query separates them."""
    build_episode(
        session,
        "richard-sutton",
        "Richard Sutton",
        date(2025, 9, 26),
        [
            "Tell me about reinforcement learning.",
            "Reinforcement learning is about reward and continual learning from experience.",
            "And the weights?",
            "In a continual learning setup the information goes into the weights.",
        ],
    )
    build_episode(
        session,
        "ada-palmer",
        "Ada Palmer",
        date(2026, 3, 6),
        [
            "Tell me about the Renaissance.",
            "The Renaissance was slower and stranger than the textbooks suggest.",
            "And printing?",
            "Gutenberg went broke because printing was a brutal business.",
        ],
    )
    return session


@pytest.fixture
def indexed(corpus: Session, search_index: OpenSearch) -> OpenSearch:
    """The same two episodes, projected into the search index."""
    project_to_search(corpus, search_index, rebuild=True)
    return search_index
