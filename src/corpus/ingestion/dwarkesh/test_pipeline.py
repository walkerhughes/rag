"""Pipeline tests against a real database, with fetching stubbed so no network is used."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from corpus.ingestion.dwarkesh import client, pipeline
from corpus.models import IngestionStatus
from storage.postgres import Base, engine, models

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parents[4]


@pytest.fixture(scope="module", autouse=True)
def schema_at_head() -> None:
    command.upgrade(Config(str(REPO_ROOT / "alembic.ini")), "head")


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(engine) as active:
        yield active
        active.rollback()
    with Session(engine) as cleanup:
        for table in (
            "transcript_segment",
            "episode_speaker",
            "episode",
            "speaker",
            "ingestion_run",
        ):
            cleanup.execute(Base.metadata.tables[table].delete())
        cleanup.commit()


def listing(slug: str = "richard-sutton") -> client.EpisodeListing:
    return client.EpisodeListing(
        slug=slug,
        title="Richard Sutton",
        canonical_url=f"https://www.dwarkesh.com/p/{slug}",
        post_date=date(2025, 9, 26),
        type="podcast",
    )


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serves the committed fixture for known slugs and fails for anything else."""

    def fetch_page(slug: str) -> str:
        path = FIXTURES / f"{slug}.html"
        if not path.exists():
            raise client.FetchError(f"{slug}: not found")
        return path.read_text()

    monkeypatch.setattr(client, "fetch_page", fetch_page)


def count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_an_episode_is_ingested_with_its_transcript(session: Session, offline: None) -> None:
    result = pipeline.ingest(session, [listing()])

    assert result.ingested == ["richard-sutton"]
    assert result.quarantined == {}

    episode = session.execute(select(models.Episode)).scalar_one()
    assert episode.title == "Richard Sutton"
    assert episode.url == "https://www.dwarkesh.com/p/richard-sutton"
    assert episode.published_at == date(2025, 9, 26)

    segments = (
        session.execute(
            select(models.TranscriptSegment)
            .where(models.TranscriptSegment.episode_id == episode.id)
            .order_by(models.TranscriptSegment.position)
        )
        .scalars()
        .all()
    )
    assert len(segments) > 100
    assert [segment.position for segment in segments] == list(range(len(segments)))
    assert count(session, models.Speaker) == 2

    run = session.execute(select(models.IngestionRun)).scalar_one()
    assert run.status == IngestionStatus.SUCCEEDED
    assert all(segment.ingestion_run_id == run.id for segment in segments)


def test_ingesting_the_same_episode_twice_changes_nothing(session: Session, offline: None) -> None:
    pipeline.ingest(session, [listing()])
    first = count(session, models.TranscriptSegment)

    pipeline.ingest(session, [listing()])

    assert count(session, models.Episode) == 1
    assert count(session, models.Speaker) == 2
    assert count(session, models.TranscriptSegment) == first


def test_an_unfetchable_episode_is_quarantined_and_the_others_still_land(
    session: Session, offline: None
) -> None:
    result = pipeline.ingest(session, [listing("missing-episode"), listing()])

    assert result.ingested == ["richard-sutton"]
    assert "missing-episode" in result.quarantined
    assert count(session, models.Episode) == 1

    run = session.execute(select(models.IngestionRun)).scalar_one()
    # The run succeeded overall, and says what it skipped.
    assert run.status == IngestionStatus.SUCCEEDED
    assert run.error is not None
    assert "missing-episode" in run.error


def test_a_run_where_everything_fails_is_recorded_as_failed(
    session: Session, offline: None
) -> None:
    result = pipeline.ingest(session, [listing("missing-episode")])

    assert result.ingested == []
    assert count(session, models.Episode) == 0

    run = session.execute(select(models.IngestionRun)).scalar_one()
    assert run.status == IngestionStatus.FAILED
    assert run.finished_at is not None


def test_a_page_with_no_transcript_leaves_no_partial_episode(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parse failure must not leave the episode row behind without its transcript."""
    monkeypatch.setattr(
        client,
        "fetch_page",
        lambda slug: '<div class="available-content"><p>Prose only.</p></div>',
    )
    result = pipeline.ingest(session, [listing()])

    assert "richard-sutton" in result.quarantined
    assert count(session, models.Episode) == 0
    assert count(session, models.TranscriptSegment) == 0
