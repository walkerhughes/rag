"""Running the examples against each retrieval strategy, and reporting what came back.

A developer-run report rather than a gate. The regression suite in
`src/retrieval/test_regression.py` is the gate, and runs ten queries against two frozen
transcripts; this measures every annotated example against whatever corpus the caller
binds, which is why the report names that corpus at the top.

The k values are fixed at one, three, five and ten. One is the hit rate, and the only
rank where precision is unbounded by the annotation. Three is roughly the number of
passages an example annotates, so precision is still informative there. Five is a
plausible context budget for an agent. Ten matches the `recall_at_10` floors in
`docs/evaluation/classes.toml` and the default limit both strategies ship with, so the
recall column is directly comparable to the contract.
"""

import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import fmean

from evaluation.dataset import Dataset, Example
from evaluation.metrics import precision_at_k, precision_ceiling, recall_at_k
from retrieval import Search

DEFAULT_K = (1, 3, 5, 10)


@dataclass(frozen=True)
class Corpus:
    """What a report measured, so a number is never mistaken for one taken elsewhere.

    The entry point fills this in, because this layer reads no database of its own.
    """

    label: str
    episodes: tuple[str, ...]
    turns: int
    chunks: int
    chunker_versions: tuple[str, ...]
    published: tuple[date, date] | None


@dataclass(frozen=True)
class Score:
    """One example, under one strategy, at one k."""

    strategy: str
    example: str
    question_class: str
    k: int
    recall: float
    precision: float
    ceiling: float

    @property
    def attainment(self) -> float:
        """Measured precision as a fraction of what the annotation allows."""
        return self.precision / self.ceiling


def measure(
    searches: Mapping[str, Search],
    examples: Sequence[Example],
    ks: Sequence[int] = DEFAULT_K,
) -> list[Score]:
    """Scores every example under every strategy, at every k."""
    depth = max(ks)

    scores: list[Score] = []
    for strategy, search in searches.items():
        for example in examples:
            # One query at the deepest k. Both strategies rank deterministically and
            # break ties on identifier, so the top k results are the first k of these.
            passages = [evidence.text for evidence in search(example.question, limit=depth)]
            phrases = example.expected_phrases
            scores.extend(
                Score(
                    strategy=strategy,
                    example=example.id,
                    question_class=example.question_class,
                    k=k,
                    recall=recall_at_k(passages, phrases, k),
                    precision=precision_at_k(passages, phrases, k),
                    ceiling=precision_ceiling(phrases, k),
                )
                for k in ks
            )
    return scores


HEADER = f"  {'strategy':<10}{'k':>3}{'recall':>10}{'precision':>11}{'ceiling':>9}{'attain':>8}"


def _table(scores: Sequence[Score]) -> list[str]:
    """A row per strategy and k, each cell an unweighted mean across the examples."""
    lines = [HEADER]
    for strategy in dict.fromkeys(score.strategy for score in scores):
        for k in sorted({score.k for score in scores}):
            group = [s for s in scores if s.strategy == strategy and s.k == k]
            lines.append(
                f"  {strategy:<10}{k:>3}"
                f"{fmean(s.recall for s in group):>10.2f}"
                f"{fmean(s.precision for s in group):>11.2f}"
                f"{fmean(s.ceiling for s in group):>9.2f}"
                f"{fmean(s.attainment for s in group):>8.2f}"
            )
    return lines


CEILING_NOTE = """\
Precision at rank k is bounded by the annotation: an example naming n phrases cannot
exceed min(n, k)/k however good the retriever is. `ceiling` is that bound and `attain` is
the measured precision as a fraction of it, so `attain` rather than `precision` is the
column to read when comparing one k against another. A phrase that occurs in more than
one passage can carry `attain` past 1.00, which says the corpus repeats the phrase.

Every cell is an unweighted mean over the examples, so each question counts once whatever
its annotation. `attain` is therefore the mean of the per-example ratios, and will not
equal a row's own `precision` divided by its own `ceiling`."""


def _wrapped(names: Sequence[str]) -> list[str]:
    """A list of identifiers, folded to a width that survives being pasted into an issue."""
    return textwrap.wrap(", ".join(names), width=88, initial_indent="  ", subsequent_indent="  ")


def _corpus_lines(corpus: Corpus) -> list[str]:
    versions = ", ".join(corpus.chunker_versions) or "none"
    window = (
        f"{corpus.published[0]} to {corpus.published[1]}" if corpus.published else "no episodes"
    )
    return [
        f"Corpus  {corpus.label}",
        f"  episodes   {len(corpus.episodes)}",
        f"  turns      {corpus.turns}",
        f"  chunks     {corpus.chunks}, chunker version {versions}",
        f"  published  {window}",
        *_wrapped(corpus.episodes),
    ]


def _dataset_lines(dataset: Dataset, scores: Sequence[Score]) -> list[str]:
    lines = [
        f"Dataset  {dataset.origin}, split {dataset.split}",
        f"  scored     {len(dataset.examples)}",
        f"  skipped    {len(dataset.unannotated)}, carrying no expected phrases",
    ]
    lines += _wrapped(dataset.unannotated)
    if not scores:
        lines.append("  nothing was scored, so no numbers follow")
    return lines


def render(corpus: Corpus, dataset: Dataset, scores: Sequence[Score]) -> str:
    """The whole report, as a block of text meant for a terminal or an issue."""
    lines = ["Retrieval evaluation", "=" * 20, ""]
    lines += [*_corpus_lines(corpus), ""]
    lines += [*_dataset_lines(dataset, scores), ""]
    if not scores:
        return "\n".join(lines)

    lines += [CEILING_NOTE, "", "Overall"]
    lines += [*_table(scores), ""]

    for question_class in sorted({score.question_class for score in scores}):
        group = [score for score in scores if score.question_class == question_class]
        examples = len({score.example for score in group})
        lines.append(f"{question_class}  {examples} examples")
        lines += [*_table(group), ""]
    return "\n".join(lines)
