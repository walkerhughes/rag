"""Writing canonical corpus records.

Saving is idempotent at the logical-record level: re-saving an episode updates it in place
and keeps the identifiers of segments that are still there, so anything derived from a
segment can continue to reference it.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from corpus.models import Episode as DomainEpisode
from corpus.models import IngestionStatus
from retrieval.chunking import CHUNKER_VERSION, Chunk
from storage.postgres import models


def start_run(session: Session, source: str) -> models.IngestionRun:
    run = models.IngestionRun(source=source, status=IngestionStatus.RUNNING)
    session.add(run)
    session.flush()
    return run


def finish_run(
    session: Session,
    run: models.IngestionRun,
    status: IngestionStatus,
    error: str | None = None,
) -> None:
    run.status = status
    run.error = error
    run.finished_at = datetime.now(UTC)
    session.flush()


def _speaker_ids(session: Session, run_id: uuid.UUID, names: list[str]) -> dict[str, uuid.UUID]:
    """Creates any speaker that does not exist yet and returns every name's identifier."""
    statement = insert(models.Speaker).values(
        [{"id": uuid.uuid4(), "name": name, "ingestion_run_id": run_id} for name in names]
    )
    session.execute(statement.on_conflict_do_nothing(index_elements=["name"]))
    rows = session.execute(
        select(models.Speaker.name, models.Speaker.id).where(models.Speaker.name.in_(names))
    ).all()
    return {name: identifier for name, identifier in rows}


def save_episode(session: Session, run: models.IngestionRun, episode: DomainEpisode) -> uuid.UUID:
    """Writes an episode and its transcript, returning the episode identifier."""
    episode_statement = insert(models.Episode).values(
        id=uuid.uuid4(),
        source_id=episode.source_id,
        title=episode.title,
        url=episode.url,
        published_at=episode.published_at,
        ingestion_run_id=run.id,
    )
    episode_id: uuid.UUID = session.execute(
        episode_statement.on_conflict_do_update(
            index_elements=["source_id"],
            set_={
                "title": episode_statement.excluded.title,
                "url": episode_statement.excluded.url,
                "published_at": episode_statement.excluded.published_at,
                "ingestion_run_id": episode_statement.excluded.ingestion_run_id,
            },
        ).returning(models.Episode.id)
    ).scalar_one()

    speakers = _speaker_ids(session, run.id, episode.speakers)

    association = insert(models.EpisodeSpeaker).values(
        [{"episode_id": episode_id, "speaker_id": speakers[name]} for name in episode.speakers]
    )
    session.execute(association.on_conflict_do_nothing(index_elements=["episode_id", "speaker_id"]))

    segment_statement = insert(models.TranscriptSegment).values(
        [
            {
                "id": uuid.uuid4(),
                "episode_id": episode_id,
                "speaker_id": speakers[segment.speaker],
                "position": segment.position,
                "text": segment.text,
                "start": segment.start,
                "ingestion_run_id": run.id,
            }
            for segment in episode.segments
        ]
    )
    session.execute(
        segment_statement.on_conflict_do_update(
            constraint="transcript_segment_position_unique",
            set_={
                "speaker_id": segment_statement.excluded.speaker_id,
                "text": segment_statement.excluded.text,
                "start": segment_statement.excluded.start,
                "ingestion_run_id": segment_statement.excluded.ingestion_run_id,
            },
        )
    )

    # A shorter transcript than last time leaves stale turns at the end.
    session.execute(
        delete(models.TranscriptSegment).where(
            models.TranscriptSegment.episode_id == episode_id,
            models.TranscriptSegment.position >= len(episode.segments),
        )
    )
    session.flush()
    return episode_id


def save_chunks(session: Session, episode_id: uuid.UUID, chunks: list[Chunk]) -> None:
    """Replaces an episode's chunks, keeping identifiers where the boundaries are unchanged."""
    if chunks:
        statement = insert(models.Chunk).values(
            [
                {
                    "id": uuid.uuid4(),
                    "episode_id": episode_id,
                    "ordinal": chunk.ordinal,
                    "first_position": chunk.first_position,
                    "last_position": chunk.last_position,
                    "speakers": chunk.speakers,
                    "text": chunk.text,
                    "start": chunk.start,
                    "chunker_version": CHUNKER_VERSION,
                }
                for chunk in chunks
            ]
        )
        session.execute(
            statement.on_conflict_do_update(
                constraint="chunk_ordinal_unique",
                set_={
                    "first_position": statement.excluded.first_position,
                    "last_position": statement.excluded.last_position,
                    "speakers": statement.excluded.speakers,
                    "text": statement.excluded.text,
                    "start": statement.excluded.start,
                    "chunker_version": statement.excluded.chunker_version,
                },
            )
        )

    # Fewer chunks than last time leaves stale ones at the end.
    session.execute(
        delete(models.Chunk).where(
            models.Chunk.episode_id == episode_id,
            models.Chunk.ordinal >= len(chunks),
        )
    )
    session.flush()
