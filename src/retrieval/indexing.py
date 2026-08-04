"""Building chunks from stored turns, and projecting them into the search index."""

import uuid

from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.orm import Session

from observability import tracer
from retrieval.bm25 import ensure_index, index_documents, recreate_index
from retrieval.chunking import Turn, chunk_turns
from retrieval.repository import save_chunks
from storage.postgres import models


def index_episode(session: Session, episode_id: uuid.UUID) -> int:
    """Reads the stored turns, chunks them, and writes the result. Returns the chunk count."""
    with tracer.start_as_current_span("chunk.episode") as span:
        span.set_attribute("episode.id", str(episode_id))

        rows = session.execute(
            select(models.TranscriptSegment, models.Speaker.name)
            .join(models.Speaker, models.TranscriptSegment.speaker_id == models.Speaker.id)
            .where(models.TranscriptSegment.episode_id == episode_id)
            .order_by(models.TranscriptSegment.position)
        ).all()
        turns = [
            Turn(
                position=row.position,
                speaker=speaker,
                text=row.text,
                start=row.start,
            )
            for row, speaker in rows
        ]

        chunks = chunk_turns(turns)
        save_chunks(session, episode_id, chunks)

        span.set_attribute("chunk.count", len(chunks))
        return len(chunks)


def index_all(session: Session) -> int:
    """Re-chunks every stored episode. Needs no network, since the turns are already here."""
    total = 0
    for episode_id in session.execute(select(models.Episode.id)).scalars().all():
        total += index_episode(session, episode_id)
    return total


def _document(chunk: models.Chunk, episode: models.Episode) -> dict[str, object]:
    return {
        "chunk_id": str(chunk.id),
        "text": chunk.text,
        "episode_source_id": episode.source_id,
        "episode_title": episode.title,
        "published_at": episode.published_at.isoformat(),
        "speakers": list(chunk.speakers),
        "first_position": chunk.first_position,
        "last_position": chunk.last_position,
        "ordinal": chunk.ordinal,
        # `is not None`, because a chunk starting at 00:00:00 is a zero timedelta, which
        # is falsy. Testing truthiness drops the timestamp of every episode's first chunk.
        "start_seconds": chunk.start.total_seconds() if chunk.start is not None else None,
    }


def project_to_search(session: Session, search: OpenSearch, *, rebuild: bool = False) -> int:
    """Copies every stored chunk into the search index.

    The index is a projection: Postgres stays canonical, so rebuilding is always safe.
    """
    with tracer.start_as_current_span("bm25.project") as span:
        if rebuild:
            recreate_index(search)
        else:
            ensure_index(search)

        rows = session.execute(
            select(models.Chunk, models.Episode).join(
                models.Episode, models.Chunk.episode_id == models.Episode.id
            )
        ).all()
        written = index_documents(search, [_document(chunk, episode) for chunk, episode in rows])
        span.set_attribute("bm25.documents", written)
        return written
