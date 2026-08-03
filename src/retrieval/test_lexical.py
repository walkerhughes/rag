"""What is Postgres's alone: tsquery construction, and the chunks the search vector covers.

The behaviour shared with the other lexical strategy is in test_contract.py.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retrieval import lexical
from retrieval.indexing import index_episode
from storage.postgres import models

pytestmark = pytest.mark.integration


def test_a_query_of_only_stopwords_returns_nothing(corpus: Session) -> None:
    """to_tsquery rejects an empty string, so a stopword-only question must not reach it."""
    assert lexical.search(corpus, "the of and") == []


def test_every_chunk_maps_onto_real_turns(corpus: Session) -> None:
    rows = corpus.execute(
        select(models.Chunk, models.Episode.source_id).join(
            models.Episode, models.Chunk.episode_id == models.Episode.id
        )
    ).all()
    assert rows

    for chunk, source_id in rows:
        turns = corpus.execute(
            select(func.count())
            .select_from(models.TranscriptSegment)
            .join(models.Episode, models.TranscriptSegment.episode_id == models.Episode.id)
            .where(
                models.Episode.source_id == source_id,
                models.TranscriptSegment.position >= chunk.first_position,
                models.TranscriptSegment.position <= chunk.last_position,
            )
        ).scalar_one()
        assert turns >= 1


def test_reindexing_unchanged_turns_changes_nothing(corpus: Session) -> None:
    """Chunk identifiers have to survive, or everything derived from them is invalidated."""
    episode_id = corpus.execute(
        select(models.Episode.id).where(models.Episode.source_id == "richard-sutton")
    ).scalar_one()
    before = set(
        corpus.execute(
            select(models.Chunk.id).where(models.Chunk.episode_id == episode_id)
        ).scalars()
    )

    index_episode(corpus, episode_id)

    after = set(
        corpus.execute(
            select(models.Chunk.id).where(models.Chunk.episode_id == episode_id)
        ).scalars()
    )
    assert before == after
