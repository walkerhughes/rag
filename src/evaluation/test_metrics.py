"""Hand-computed metrics.

Every expected value here was worked out on paper. A metric wrong in the third decimal
place would be believed, so these assert exact numbers rather than a direction of travel.
"""

import pytest

from evaluation.metrics import normalise, precision_at_k, precision_ceiling, recall_at_k

# Passage 0 holds the first phrase, passages 2 and 3 both hold the second, passage 1
# holds neither. Two of the four are worded so that only case-folded, whitespace-collapsed
# comparison finds the phrase.
PASSAGES = [
    "The information goes into the weights.",
    "Reward is the signal that drives everything.",
    "A bitter lesson about   search\nand learning.",
    "The Bitter Lesson, again.",
]
PHRASES = ["goes into the weights", "bitter lesson"]


def test_recall_is_phrases_found_over_phrases_expected() -> None:
    # Top 1 reaches the first phrase only; top 3 reaches both.
    assert recall_at_k(PASSAGES, PHRASES, 1) == 0.5
    assert recall_at_k(PASSAGES, PHRASES, 2) == 0.5
    assert recall_at_k(PASSAGES, PHRASES, 3) == 1.0


def test_a_phrase_in_several_passages_counts_once() -> None:
    """Recall asks whether a phrase was surfaced, not how often."""
    assert recall_at_k(PASSAGES, PHRASES, 4) == 1.0


def test_precision_is_relevant_passages_over_k() -> None:
    # One relevant passage in the top 2, two in the top 3, three in the top 4.
    assert precision_at_k(PASSAGES, PHRASES, 1) == 1.0
    assert precision_at_k(PASSAGES, PHRASES, 2) == 0.5
    assert precision_at_k(PASSAGES, PHRASES, 3) == pytest.approx(2 / 3)
    assert precision_at_k(PASSAGES, PHRASES, 4) == 0.75


def test_a_passage_holding_two_phrases_counts_once() -> None:
    both = ["It goes into the weights, which is the bitter lesson."]
    assert precision_at_k(both, PHRASES, 1) == 1.0
    assert recall_at_k(both, PHRASES, 1) == 1.0


def test_precision_divides_by_k_even_when_fewer_results_came_back() -> None:
    """Returning three passages when ten were asked for is not rewarded."""
    assert precision_at_k(PASSAGES, PHRASES, 10) == 0.3
    assert recall_at_k(PASSAGES, PHRASES, 10) == 1.0


def test_no_results_scores_zero() -> None:
    assert recall_at_k([], PHRASES, 10) == 0.0
    assert precision_at_k([], PHRASES, 10) == 0.0


def test_the_ceiling_is_what_the_annotation_allows() -> None:
    """Two annotated phrases cannot fill more than two of the top ten."""
    assert precision_ceiling(PHRASES, 1) == 1.0
    assert precision_ceiling(PHRASES, 2) == 1.0
    assert precision_ceiling(PHRASES, 3) == pytest.approx(2 / 3)
    assert precision_ceiling(PHRASES, 10) == 0.2
    assert precision_ceiling(["one"], 10) == 0.1


def test_a_repeated_phrase_can_carry_precision_past_the_ceiling() -> None:
    """The wart the report names: the ceiling counts phrases, the corpus counts passages."""
    assert precision_at_k(PASSAGES, PHRASES, 4) > precision_ceiling(PHRASES, 4)


def test_matching_folds_case_and_collapses_whitespace() -> None:
    assert normalise("  The\nBitter   Lesson ") == "the bitter lesson"
    assert recall_at_k(["A bitter lesson about   search\nand learning."], ["Search And"], 1) == 1.0


def test_an_example_with_no_expected_phrases_is_not_scorable() -> None:
    """Scoring it zero would read as a retrieval failure rather than a missing annotation."""
    for call in (recall_at_k, precision_at_k):
        with pytest.raises(ValueError, match="no expected phrases"):
            call(PASSAGES, [], 10)
    with pytest.raises(ValueError, match="no expected phrases"):
        precision_ceiling([], 10)


def test_a_rank_below_one_is_rejected() -> None:
    for k in (0, -1):
        with pytest.raises(ValueError, match="at least one"):
            recall_at_k(PASSAGES, PHRASES, k)
        with pytest.raises(ValueError, match="at least one"):
            precision_at_k(PASSAGES, PHRASES, k)
        with pytest.raises(ValueError, match="at least one"):
            precision_ceiling(PHRASES, k)
