"""Writing chunks.

Owned by the retrieval layer, so that storage holds the schema and nothing about how
passages are cut. Replacing the chunking rules touches this layer alone.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from retrieval.chunking import CHUNKER_VERSION, Chunk
from storage.postgres import models


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
