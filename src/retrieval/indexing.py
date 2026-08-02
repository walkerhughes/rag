"""Building an episode's chunks from the turns already stored."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpus.models import TranscriptSegment
from observability import tracer
from retrieval.chunking import chunk_segments
from storage.postgres import models, repositories


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
        segments = [
            TranscriptSegment(
                position=row.position,
                speaker=speaker,
                text=row.text,
                start=row.start,
            )
            for row, speaker in rows
        ]

        chunks = chunk_segments(segments)
        repositories.save_chunks(session, episode_id, chunks)

        span.set_attribute("chunk.count", len(chunks))
        return len(chunks)


def index_all(session: Session) -> int:
    """Re-chunks every stored episode. Needs no network, since the turns are already here."""
    total = 0
    for episode_id in session.execute(select(models.Episode.id)).scalars().all():
        total += index_episode(session, episode_id)
    return total
