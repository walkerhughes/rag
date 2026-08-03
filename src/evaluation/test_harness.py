"""Running and reporting, against strategies that return canned passages.

No database and no network: a `Search` is a callable returning `Evidence`, so a stub
satisfies the contract and the aggregation can be checked against numbers worked out by
hand.
"""

import uuid
from datetime import date
from pathlib import Path

import pytest

from evaluation.dataset import Dataset, Example
from evaluation.harness import Corpus, Score, measure, render
from retrieval import Evidence, Search

EXAMPLES = (
    Example("direct-001", "direct_retrieval", "where does it go?", ("into the weights",)),
    Example("hop-001", "bounded_multi_hop", "who taught whom?", ("bitter lesson",)),
)


def evidence(text: str) -> Evidence:
    return Evidence(
        chunk_id=uuid.uuid4(),
        episode_source_id="richard-sutton",
        episode_title="Richard Sutton",
        published_at=date(2025, 9, 26),
        speakers=["Richard Sutton"],
        text=text,
        first_position=0,
        last_position=1,
        start=None,
        score=1.0,
        strategy="stub",
    )


def perfect(query: str, *, limit: int = 10, **_: object) -> list[Evidence]:
    """Puts the answer first, then filler."""
    answer = "into the weights" if "go" in query else "bitter lesson"
    return [evidence(answer), *(evidence("filler") for _ in range(limit - 1))]


def useless(query: str, *, limit: int = 10, **_: object) -> list[Evidence]:
    return [evidence("filler") for _ in range(limit)]


@pytest.fixture
def searches() -> dict[str, Search]:
    return {"perfect": perfect, "useless": useless}


def test_every_example_is_scored_under_every_strategy_at_every_k(
    searches: dict[str, Search],
) -> None:
    scores = measure(searches, EXAMPLES, (1, 10))
    assert len(scores) == 2 * len(EXAMPLES) * 2
    assert {score.strategy for score in scores} == {"perfect", "useless"}


def test_scores_are_what_the_stubs_earn(searches: dict[str, Search]) -> None:
    scores = {(s.strategy, s.example, s.k): s for s in measure(searches, EXAMPLES, (1, 10))}

    # One phrase, found at rank one: full recall, and precision of one in ten at k=10.
    assert scores[("perfect", "direct-001", 1)].recall == 1.0
    assert scores[("perfect", "direct-001", 1)].precision == 1.0
    assert scores[("perfect", "direct-001", 10)].recall == 1.0
    assert scores[("perfect", "direct-001", 10)].precision == 0.1
    # Which is everything the annotation allows, so attainment is full.
    assert scores[("perfect", "direct-001", 10)].ceiling == 0.1
    assert scores[("perfect", "direct-001", 10)].attainment == 1.0

    assert scores[("useless", "hop-001", 10)].recall == 0.0
    assert scores[("useless", "hop-001", 10)].precision == 0.0


def test_a_strategy_returning_less_than_k_is_still_scored_against_k() -> None:
    """Returning one result, or none, is a weak answer rather than a small denominator."""

    def thin(query: str, *, limit: int = 10, **_: object) -> list[Evidence]:
        return [evidence("into the weights")]

    def empty(query: str, *, limit: int = 10, **_: object) -> list[Evidence]:
        return []

    scores = {s.strategy: s for s in measure({"thin": thin, "empty": empty}, EXAMPLES[:1], (10,))}
    assert (scores["thin"].recall, scores["thin"].precision) == (1.0, 0.1)
    assert (scores["empty"].recall, scores["empty"].precision) == (0.0, 0.0)


def test_a_deeper_k_is_queried_once_and_sliced() -> None:
    """One query per example per strategy, whatever the k values."""
    queried = []

    def counting(query: str, *, limit: int = 10, **_: object) -> list[Evidence]:
        queried.append(limit)
        return [evidence("into the weights")]

    measure({"counting": counting}, EXAMPLES[:1], (1, 3, 5, 10))
    assert queried == [10]


def test_measuring_at_no_k_at_all_is_refused(searches: dict[str, Search]) -> None:
    """Not quietly defaulted: a depth nobody asked for would be scored and believed."""
    with pytest.raises(ValueError):
        measure(searches, EXAMPLES, ())


CORPUS = Corpus(
    label="a stub",
    episodes=("richard-sutton",),
    turns=4,
    chunks=2,
    chunker_versions=("v1",),
    published=(date(2025, 9, 26), date(2026, 3, 6)),
)


def dataset(unannotated: tuple[str, ...] = ()) -> Dataset:
    return Dataset(Path("examples.jsonl"), "dev", EXAMPLES, unannotated)


def test_the_report_names_the_corpus_it_measured(searches: dict[str, Search]) -> None:
    """A number taken on one corpus must never be mistaken for one taken on another."""
    report = render(CORPUS, dataset(), measure(searches, EXAMPLES, (1, 10)))
    assert "a stub" in report
    assert "richard-sutton" in report
    assert "chunker version v1" in report
    assert "2025-09-26 to 2026-03-06" in report


def test_the_report_breaks_down_by_strategy_and_class(searches: dict[str, Search]) -> None:
    report = render(CORPUS, dataset(), measure(searches, EXAMPLES, (1, 10)))
    assert "Overall" in report
    assert "direct_retrieval  1 examples" in report
    assert "bounded_multi_hop  1 examples" in report
    # The perfect stub reaches every phrase at rank one; the useless one reaches none.
    assert "  perfect     1      1.00       1.00     1.00    1.00" in report
    assert "  useless     1      0.00       0.00     1.00    0.00" in report


def test_every_cell_is_an_unweighted_mean_over_the_examples() -> None:
    """Two examples that disagree, so a mean is not a maximum, a minimum or a total.

    `attain` is the mean of the per-example ratios, not the ratio of the means: the row
    below prints 0.50 where its own precision over its own ceiling would give 0.33.
    """
    scores = [
        Score("s", "found", "direct_retrieval", 10, recall=1.0, precision=0.1, ceiling=0.1),
        Score("s", "missed", "direct_retrieval", 10, recall=0.0, precision=0.0, ceiling=0.2),
    ]
    report = render(CORPUS, dataset(), scores)
    assert "  s          10      0.50       0.05     0.15    0.50" in report
    assert "unweighted mean" in report


def test_the_report_says_what_it_skipped() -> None:
    report = render(CORPUS, dataset(("stance-004",)), [])
    assert "skipped    1" in report
    assert "stance-004" in report
    assert "nothing was scored" in report


def test_the_report_explains_the_precision_ceiling(searches: dict[str, Search]) -> None:
    """A low precision without its ceiling invites a wrong conclusion about the retriever."""
    report = render(CORPUS, dataset(), measure(searches, EXAMPLES, (1, 10)))
    assert "min(n, k)/k" in report


def test_attainment_is_precision_over_what_the_annotation_allows() -> None:
    score = Score("s", "e", "c", 10, recall=1.0, precision=0.1, ceiling=0.2)
    assert score.attainment == 0.5


def test_a_repeated_phrase_carries_attainment_past_full_marks() -> None:
    """The wart the report names: the ceiling counts phrases, the corpus counts passages."""

    def repeating(query: str, *, limit: int = 10, **_: object) -> list[Evidence]:
        return [evidence("bitter lesson"), evidence("the bitter lesson, again")]

    (score,) = measure({"repeating": repeating}, EXAMPLES[1:], (2,))
    assert (score.precision, score.ceiling, score.attainment) == (1.0, 0.5, 2.0)
    # Reported rather than clamped, because it is the corpus that repeats the phrase.
    assert "    2.00" in render(CORPUS, dataset(), [score])
