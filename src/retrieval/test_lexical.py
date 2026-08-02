"""Retrieval tests against a real database, since the search vector is Postgres's job."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from corpus.models import Episode, TranscriptSegment
from retrieval import lexical
from retrieval.indexing import index_episode
from storage.postgres import models, repositories

pytestmark = pytest.mark.integration


def build(
    session: Session,
    source_id: str,
    speaker: str,
    published: date,
    texts: list[str],
) -> None:
    run = repositories.start_run(session, "test")
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
    episode_id = repositories.save_episode(session, run, episode)
    index_episode(session, episode_id)


@pytest.fixture
def corpus(session: Session) -> Session:
    build(
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
    build(
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


def test_a_match_carries_everything_needed_to_cite_it(corpus: Session) -> None:
    found = lexical.search(corpus, "reinforcement learning reward")

    assert found
    top = found[0]
    assert top.episode_source_id == "richard-sutton"
    assert top.published_at == date(2025, 9, 26)
    assert "Richard Sutton" in top.speakers
    assert top.first_position <= top.last_position
    assert top.start is not None
    assert top.score > 0
    assert top.strategy == "lexical"


def test_repeating_a_query_returns_the_same_order(corpus: Session) -> None:
    """Ranked results must be reproducible, or an evaluation measures noise."""
    first = lexical.search(corpus, "learning", limit=5)
    second = lexical.search(corpus, "learning", limit=5)
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]


def test_a_natural_language_question_still_matches(corpus: Session) -> None:
    """Requiring every term makes a question unmatchable, which is the failure to avoid."""
    question = "Where does Richard Sutton say the information goes in continual learning?"
    assert lexical.search(corpus, question)


def test_the_episode_filter_narrows_results(corpus: Session) -> None:
    found = lexical.search(corpus, "learning renaissance", episodes=["ada-palmer"])
    assert found
    assert {item.episode_source_id for item in found} == {"ada-palmer"}


def test_the_speaker_filter_narrows_results(corpus: Session) -> None:
    found = lexical.search(corpus, "learning renaissance", speakers=["Ada Palmer"])
    assert found
    assert all("Ada Palmer" in item.speakers for item in found)


def test_the_date_filters_narrow_results(corpus: Session) -> None:
    before = lexical.search(corpus, "learning renaissance", published_before=date(2025, 12, 31))
    assert {item.episode_source_id for item in before} == {"richard-sutton"}

    after = lexical.search(corpus, "learning renaissance", published_after=date(2026, 1, 1))
    assert {item.episode_source_id for item in after} == {"ada-palmer"}


def test_a_query_of_only_stopwords_returns_nothing(corpus: Session) -> None:
    assert lexical.search(corpus, "the of and") == []
    assert lexical.search(corpus, "") == []


def test_the_limit_is_respected(corpus: Session) -> None:
    assert len(lexical.search(corpus, "learning renaissance printing", limit=2)) <= 2


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
