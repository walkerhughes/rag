"""Constraint and persistence tests for the canonical corpus. These need the database."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from corpus.models import Episode as DomainEpisode
from corpus.models import IngestionStatus, TranscriptSegment
from storage.postgres import models, repositories

pytestmark = pytest.mark.integration


def sutton(segments: list[TranscriptSegment] | None = None) -> DomainEpisode:
    return DomainEpisode(
        source_id="richard-sutton",
        title="Richard Sutton",
        url="https://www.dwarkesh.com/p/richard-sutton",
        published_at=date(2025, 9, 26),
        segments=[
            TranscriptSegment(position=0, speaker="Dwarkesh Patel", text="A question."),
            TranscriptSegment(
                position=1,
                speaker="Richard Sutton",
                text="It goes into the weights.",
                start=timedelta(minutes=31, seconds=4),
            ),
        ]
        if segments is None
        else segments,
    )


def count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_saving_an_episode_stores_the_transcript_in_order(session: Session) -> None:
    run = repositories.start_run(session, "dwarkesh")
    episode_id = repositories.save_episode(session, run, sutton())
    repositories.finish_run(session, run, IngestionStatus.SUCCEEDED)

    segments = (
        session.execute(
            select(models.TranscriptSegment)
            .where(models.TranscriptSegment.episode_id == episode_id)
            .order_by(models.TranscriptSegment.position)
        )
        .scalars()
        .all()
    )

    assert [s.position for s in segments] == [0, 1]
    assert segments[1].text == "It goes into the weights."
    assert segments[1].start == timedelta(minutes=31, seconds=4)
    assert segments[0].speaker_id != segments[1].speaker_id
    # Every durable record carries the run that produced it.
    assert all(s.ingestion_run_id == run.id for s in segments)


def test_resaving_the_same_episode_creates_no_duplicates(session: Session) -> None:
    """Re-ingesting unchanged source data must not double the corpus."""
    first = repositories.start_run(session, "dwarkesh")
    episode_id = repositories.save_episode(session, first, sutton())
    segment_ids = set(
        session.execute(
            select(models.TranscriptSegment.id).where(
                models.TranscriptSegment.episode_id == episode_id
            )
        ).scalars()
    )

    second = repositories.start_run(session, "dwarkesh")
    assert repositories.save_episode(session, second, sutton()) == episode_id

    assert count(session, models.Episode) == 1
    assert count(session, models.Speaker) == 2
    assert count(session, models.TranscriptSegment) == 2
    # Identifiers survive, so anything derived from a segment still points at it.
    assert (
        set(
            session.execute(
                select(models.TranscriptSegment.id).where(
                    models.TranscriptSegment.episode_id == episode_id
                )
            ).scalars()
        )
        == segment_ids
    )


def test_a_shorter_transcript_removes_the_stale_turns(session: Session) -> None:
    run = repositories.start_run(session, "dwarkesh")
    repositories.save_episode(session, run, sutton())
    repositories.save_episode(
        session,
        run,
        sutton(
            segments=[TranscriptSegment(position=0, speaker="Dwarkesh Patel", text="Only one.")]
        ),
    )
    assert count(session, models.TranscriptSegment) == 1


def test_two_turns_cannot_share_a_position(session: Session) -> None:
    run = repositories.start_run(session, "dwarkesh")
    episode_id = repositories.save_episode(session, run, sutton())
    speaker_id = session.execute(select(models.Speaker.id)).scalars().first()

    session.add(
        models.TranscriptSegment(
            episode_id=episode_id,
            speaker_id=speaker_id,
            position=0,
            text="A different turn at the same position.",
            ingestion_run_id=run.id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_two_episodes_cannot_share_a_source_id(session: Session) -> None:
    run = repositories.start_run(session, "dwarkesh")
    repositories.save_episode(session, run, sutton())
    session.add(
        models.Episode(
            source_id="richard-sutton",
            title="A different title",
            url="https://example.com",
            published_at=date(2026, 1, 1),
            ingestion_run_id=run.id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_repeated_turn_at_a_new_position_is_kept(session: Session) -> None:
    """Short turns legitimately repeat, so identical text is not itself a duplicate."""
    run = repositories.start_run(session, "dwarkesh")
    repositories.save_episode(
        session,
        run,
        sutton(
            [
                TranscriptSegment(position=0, speaker="Dwarkesh Patel", text="Right."),
                TranscriptSegment(position=1, speaker="Richard Sutton", text="A turn."),
                TranscriptSegment(position=2, speaker="Dwarkesh Patel", text="Right."),
            ]
        ),
    )
    assert count(session, models.TranscriptSegment) == 3


def test_a_segment_requires_a_real_episode(session: Session) -> None:
    run = repositories.start_run(session, "dwarkesh")
    speaker = models.Speaker(name="Nobody", ingestion_run_id=run.id)
    session.add(speaker)
    session.flush()

    session.add(
        models.TranscriptSegment(
            episode_id=uuid.uuid4(),
            speaker_id=speaker.id,
            position=0,
            text="Orphan.",
            ingestion_run_id=run.id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_failed_run_is_recorded_rather_than_discarded(session: Session) -> None:
    run = repositories.start_run(session, "dwarkesh")
    repositories.finish_run(session, run, IngestionStatus.FAILED, error="parser matched no turns")
    session.commit()

    stored = session.get(models.IngestionRun, run.id)
    assert stored is not None
    assert stored.status == IngestionStatus.FAILED
    assert stored.error == "parser matched no turns"
    assert stored.finished_at is not None
