"""BM25 tests against a real OpenSearch, since ranking is the thing under test."""

from datetime import date, timedelta

import pytest
from opensearchpy import OpenSearch
from sqlalchemy.orm import Session

from corpus import repository
from corpus.models import Episode, TranscriptSegment
from retrieval import bm25
from retrieval.indexing import index_episode, project_to_search
from storage.postgres import models

pytestmark = pytest.mark.integration


def build(
    session: Session, source_id: str, speaker: str, published: date, texts: list[str]
) -> None:
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
def indexed(session: Session, search_index: OpenSearch) -> OpenSearch:
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
    project_to_search(session, search_index, rebuild=True)
    return search_index


def test_a_match_carries_everything_needed_to_cite_it(indexed: OpenSearch) -> None:
    found = bm25.search_chunks(indexed, "reinforcement learning reward")

    assert found
    top = found[0]
    assert top.episode_source_id == "richard-sutton"
    assert top.published_at == date(2025, 9, 26)
    assert "Richard Sutton" in top.speakers
    assert top.first_position <= top.last_position
    assert top.start is not None
    assert top.score > 0
    assert top.strategy == "bm25"


def test_the_same_contract_comes_back_as_from_postgres(
    indexed: OpenSearch, session: Session
) -> None:
    """Both strategies answer with Evidence, which is what lets them be compared."""
    from retrieval import lexical

    query = "continual learning weights"
    assert {type(item) for item in bm25.search_chunks(indexed, query)} == {
        type(item) for item in lexical.search(session, query)
    }


def test_repeating_a_query_returns_the_same_order(indexed: OpenSearch) -> None:
    first = bm25.search_chunks(indexed, "learning", limit=5)
    second = bm25.search_chunks(indexed, "learning", limit=5)
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]


def test_a_natural_language_question_matches(indexed: OpenSearch) -> None:
    question = "Where does Richard Sutton say the information goes in continual learning?"
    assert bm25.search_chunks(indexed, question)


def test_filters_narrow_results(indexed: OpenSearch) -> None:
    assert {
        item.episode_source_id
        for item in bm25.search_chunks(indexed, "learning renaissance", episodes=["ada-palmer"])
    } == {"ada-palmer"}
    assert all(
        "Ada Palmer" in item.speakers
        for item in bm25.search_chunks(indexed, "renaissance", speakers=["Ada Palmer"])
    )
    assert {
        item.episode_source_id
        for item in bm25.search_chunks(
            indexed, "learning renaissance", published_before=date(2025, 12, 31)
        )
    } == {"richard-sutton"}


def test_an_empty_query_returns_nothing(indexed: OpenSearch) -> None:
    assert bm25.search_chunks(indexed, "") == []
    assert bm25.search_chunks(indexed, "   ") == []


def test_the_limit_is_respected(indexed: OpenSearch) -> None:
    assert len(bm25.search_chunks(indexed, "learning renaissance printing", limit=2)) <= 2


def test_the_index_rebuilds_from_postgres(indexed: OpenSearch, session: Session) -> None:
    """The index is a projection, so losing it entirely must cost nothing but time."""
    before = indexed.count(index=bm25.INDEX)["count"]
    indexed.indices.delete(index=bm25.INDEX)

    project_to_search(session, indexed, rebuild=True)

    assert indexed.count(index=bm25.INDEX)["count"] == before


def test_chunk_identifiers_are_shared_with_postgres(indexed: OpenSearch, session: Session) -> None:
    """A citation resolves through the same identifier whichever strategy found it."""
    from sqlalchemy import select

    stored = set(session.execute(select(models.Chunk.id)).scalars())
    found = bm25.search_chunks(indexed, "learning renaissance printing", limit=20)
    assert found
    assert all(item.chunk_id in stored for item in found)


def test_a_chunk_starting_at_zero_keeps_its_timestamp(indexed: OpenSearch) -> None:
    """A zero timedelta is falsy, so a truthiness test loses every first chunk's start."""
    found = bm25.search_chunks(indexed, "reinforcement learning", limit=20)
    starts = [item.start for item in found if item.first_position == 0]
    assert starts
    assert all(start is not None for start in starts)
    assert timedelta(0) in starts
