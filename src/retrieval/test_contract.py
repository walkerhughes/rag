"""The behaviour every lexical strategy owes, asserted once and run against each.

Both strategies answer with `Evidence` over the same chunks, so a property that holds for
one has to hold for the other. Anything true of a single strategy belongs in that
strategy's own tests instead.
"""

from datetime import date
from functools import partial

import pytest
from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.orm import Session

from retrieval import Search, bm25, lexical
from storage.postgres import models

pytestmark = pytest.mark.integration


@pytest.fixture(params=[lexical.STRATEGY, bm25.STRATEGY])
def strategy(
    request: pytest.FixtureRequest, corpus: Session, indexed: OpenSearch
) -> tuple[str, Search]:
    """Each strategy in turn, as the name it stamps on `Evidence` and a bound search."""
    name: str = request.param
    searches: dict[str, Search] = {
        lexical.STRATEGY: partial(lexical.search, corpus),
        bm25.STRATEGY: partial(bm25.search, indexed),
    }
    return name, searches[name]


def test_a_match_carries_everything_needed_to_cite_it(strategy: tuple[str, Search]) -> None:
    name, search = strategy
    found = search("reinforcement learning reward")

    assert found
    top = found[0]
    assert top.episode_source_id == "richard-sutton"
    assert top.published_at == date(2025, 9, 26)
    assert "Richard Sutton" in top.speakers
    assert top.first_position <= top.last_position
    assert top.start is not None
    assert top.score > 0
    assert top.strategy == name


def test_repeating_a_query_returns_the_same_order(strategy: tuple[str, Search]) -> None:
    """Ranked results must be reproducible, or an evaluation measures noise."""
    _, search = strategy
    first = search("learning", limit=5)
    second = search("learning", limit=5)
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]


def test_a_natural_language_question_still_matches(strategy: tuple[str, Search]) -> None:
    """Requiring every term makes a question unmatchable, which is the failure to avoid."""
    _, search = strategy
    question = "Where does Richard Sutton say the information goes in continual learning?"
    assert search(question)


def test_the_episode_filter_narrows_results(strategy: tuple[str, Search]) -> None:
    _, search = strategy
    found = search("learning renaissance", episodes=["ada-palmer"])
    assert found
    assert {item.episode_source_id for item in found} == {"ada-palmer"}


def test_the_speaker_filter_narrows_results(strategy: tuple[str, Search]) -> None:
    _, search = strategy
    found = search("learning renaissance", speakers=["Ada Palmer"])
    assert found
    assert all("Ada Palmer" in item.speakers for item in found)


def test_the_date_filters_narrow_results(strategy: tuple[str, Search]) -> None:
    _, search = strategy
    before = search("learning renaissance", published_before=date(2025, 12, 31))
    assert {item.episode_source_id for item in before} == {"richard-sutton"}

    after = search("learning renaissance", published_after=date(2026, 1, 1))
    assert {item.episode_source_id for item in after} == {"ada-palmer"}


def test_the_limit_is_respected(strategy: tuple[str, Search]) -> None:
    _, search = strategy
    assert len(search("learning renaissance printing", limit=2)) <= 2


def test_an_empty_query_returns_nothing(strategy: tuple[str, Search]) -> None:
    _, search = strategy
    assert search("") == []
    assert search("   ") == []


def test_a_result_resolves_to_a_stored_chunk(strategy: tuple[str, Search], corpus: Session) -> None:
    """A citation resolves through the same identifier whichever strategy found it."""
    _, search = strategy
    stored = set(corpus.execute(select(models.Chunk.id)).scalars())
    found = search("learning renaissance printing", limit=20)
    assert found
    assert all(item.chunk_id in stored for item in found)
