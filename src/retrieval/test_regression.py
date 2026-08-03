"""Retrieval quality gate.

Runs fixed queries against a frozen corpus and fails when recall drops. The corpus is
built from the committed transcript fixtures rather than from ingested episodes, because
a suite that reads the live archive measures the corpus rather than the retriever: a
newly published episode would move the numbers and a green run would mean nothing.

Assertions name a phrase rather than a chunk identifier, so changing the chunking rules
is allowed to move boundaries but is not allowed to lose the passage.
"""

import json
from datetime import date, timedelta
from functools import partial
from pathlib import Path

import pytest
from opensearchpy import OpenSearch
from sqlalchemy.orm import Session

from corpus import repository
from corpus.ingestion.dwarkesh.parser import parse_transcript
from corpus.models import Episode
from retrieval import Evidence, Search, bm25, lexical
from retrieval.indexing import index_episode, project_to_search

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "corpus/ingestion/dwarkesh/fixtures"
QUERIES = Path(__file__).parents[2] / "docs/evaluation/retrieval_regression.jsonl"

FROZEN = {
    "richard-sutton": date(2025, 9, 26),
    "grant-sanderson-2": date(2026, 6, 30),
}

# Measured on the frozen corpus: both strategies reach 1.00 at ten and 0.90 at three, so
# each floor has a query of headroom. A gate only at ten cannot fire until retrieval is
# badly broken, which is why three is here too. Raise a floor when a change earns it;
# never lower one to make a failing run pass.
RECALL_FLOORS = {3: 0.8, 10: 0.9}


def cases() -> list[dict[str, str]]:
    return [json.loads(line) for line in QUERIES.read_text().splitlines() if line.strip()]


@pytest.fixture(scope="function")
def frozen_corpus(session: Session, search_index: OpenSearch) -> OpenSearch:
    """The committed transcripts, ingested through the real parser and chunker."""
    run = repository.start_run(session, "regression")
    for slug, published in FROZEN.items():
        segments = parse_transcript((FIXTURES / f"{slug}.html").read_text())
        episode = Episode(
            source_id=slug,
            title=slug,
            url=f"https://www.dwarkesh.com/p/{slug}",
            published_at=published,
            segments=segments,
        )
        index_episode(session, repository.save_episode(session, run, episode))
    project_to_search(session, search_index, rebuild=True)
    return search_index


@pytest.fixture(params=[lexical.STRATEGY, bm25.STRATEGY])
def strategy(
    request: pytest.FixtureRequest, session: Session, frozen_corpus: OpenSearch
) -> tuple[str, Search]:
    """Each strategy in turn, bound to the frozen corpus."""
    name: str = request.param
    searches: dict[str, Search] = {
        lexical.STRATEGY: partial(lexical.search, session),
        bm25.STRATEGY: partial(bm25.search, frozen_corpus),
    }
    return name, searches[name]


def found(results: list[Evidence], case: dict[str, str]) -> bool:
    return any(
        item.episode_source_id == case["expected_episode"]
        and case["expected_phrase"].lower() in item.text.lower()
        for item in results
    )


def recall(strategy: Search, k: int) -> tuple[float, list[str]]:
    misses = []
    for case in cases():
        if not found(strategy(case["query"], limit=k), case):
            misses.append(f"{case['id']}: {case['query']}")
    return 1 - len(misses) / len(cases()), misses


def test_the_frozen_corpus_is_what_the_fixtures_describe(frozen_corpus: OpenSearch) -> None:
    """A corpus that silently changed would make every number below meaningless."""
    assert frozen_corpus.count(index=bm25.INDEX)["count"] > 100


def test_recall_has_not_regressed(strategy: tuple[str, Search]) -> None:
    name, search = strategy
    for k, floor in RECALL_FLOORS.items():
        score, misses = recall(search, k)
        assert score >= floor, (
            f"{name} Recall@{k}={score:.2f} below {floor}, missed:\n  " + "\n  ".join(misses)
        )


def test_the_gate_can_actually_fire(session: Session, frozen_corpus: OpenSearch) -> None:
    """A floor nothing can fail is not a gate.

    Postgres reaches only 0.40 at rank one against 0.90 for BM25, the term-rarity gap.
    If this ever passes, the floors are measuring nothing and need tightening.
    """
    score, _ = recall(partial(lexical.search, session), 1)
    assert score < RECALL_FLOORS[3]


def test_an_exact_phrase_ranks_first(strategy: tuple[str, Search]) -> None:
    """A distinctive quoted phrase is the easiest case there is; failing it means breakage."""
    _, search = strategy
    results = search("In a continual learning setup the information goes into the weights", limit=3)
    assert results
    assert results[0].episode_source_id == "richard-sutton"


def test_every_result_can_be_cited(strategy: tuple[str, Search]) -> None:
    """Retrieval that cannot be resolved back to a transcript position is unusable."""
    _, search = strategy
    results = search("continual learning reward", limit=10)
    assert results
    for item in results:
        assert item.episode_source_id
        assert item.first_position <= item.last_position
        assert item.speakers
        assert item.start is None or isinstance(item.start, timedelta)


def test_filters_do_not_leak_across_episodes(strategy: tuple[str, Search]) -> None:
    _, search = strategy
    results = search("learning mathematics", episodes=["grant-sanderson-2"], limit=10)
    assert results
    assert {item.episode_source_id for item in results} == {"grant-sanderson-2"}
