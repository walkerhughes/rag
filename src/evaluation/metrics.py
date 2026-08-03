"""Precision and recall at k, scored by phrase containment.

A passage is relevant when it contains one of the example's expected phrases. Comparison
folds case and collapses whitespace, matching how the regression suite compares, so a
line break inside a retrieved chunk does not hide a phrase that is present.

These three functions are the whole arithmetic of the report. A metric wrong in the third
decimal place would be believed, which is why they take plain strings and are covered by
hand-computed tests rather than by a run against the database.
"""

from collections.abc import Sequence


def normalise(text: str) -> str:
    """Lowercased, with every run of whitespace collapsed to a single space."""
    return " ".join(text.lower().split())


def _depth(k: int) -> int:
    if k < 1:
        raise ValueError("k must be at least one")
    return k


def _top(passages: Sequence[str], k: int) -> list[str]:
    return [normalise(passage) for passage in passages[: _depth(k)]]


def _phrases(phrases: Sequence[str]) -> list[str]:
    if not phrases:
        raise ValueError("an example with no expected phrases cannot be scored")
    return [normalise(phrase) for phrase in phrases]


def recall_at_k(passages: Sequence[str], phrases: Sequence[str], k: int) -> float:
    """Expected phrases appearing somewhere in the top k passages, over phrases expected.

    A phrase found in several passages counts once: the question is whether retrieval
    surfaced it at all.
    """
    top = _top(passages, k)
    wanted = _phrases(phrases)
    found = sum(1 for phrase in wanted if any(phrase in passage for passage in top))
    return found / len(wanted)


def precision_at_k(passages: Sequence[str], phrases: Sequence[str], k: int) -> float:
    """Top k passages holding at least one expected phrase, over k.

    The denominator is k rather than the number of results returned, so a strategy that
    returns three passages when ten were asked for is not rewarded for returning less.
    """
    top = _top(passages, k)
    wanted = _phrases(phrases)
    relevant = sum(1 for passage in top if any(phrase in passage for phrase in wanted))
    return relevant / k


def precision_ceiling(phrases: Sequence[str], k: int) -> float:
    """The highest Precision@k this example's annotation allows.

    An example annotating two passages cannot exceed 0.2 at k=10 however good the
    retriever is, so a bare precision number invites the wrong conclusion. The ceiling
    assumes each expected phrase lies in one passage; a phrase repeated across passages
    can carry the measured value past it, which is a property of the corpus rather than a
    fault in the arithmetic.
    """
    return min(len(_phrases(phrases)), _depth(k)) / k
