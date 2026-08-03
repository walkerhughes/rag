"""Measurement of retrieval against the evaluation examples.

Evaluation reads the retrieval contract and the example files, and writes nothing. It
sits above retrieval for the same reason a test sits above the code it covers: measuring
a strategy means calling it, and a strategy must never know it is being measured.

The shapes here are what a caller supplies. `Example` is one annotated question reduced
to what a retrieval score needs, and `Corpus` is the description of what was searched,
which the entry point fills in because this layer does not read the database.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Example:
    """One question and the verbatim phrases a correct retrieval must surface.

    Ground truth is a phrase rather than a chunk identifier, so re-chunking is allowed to
    move a boundary but is not allowed to lose the passage.
    """

    id: str
    question_class: str
    question: str
    expected_phrases: tuple[str, ...]


@dataclass(frozen=True)
class Corpus:
    """What a report measured, so a number is never mistaken for one taken elsewhere."""

    label: str
    episodes: tuple[str, ...]
    turns: int
    chunks: int
    chunker_versions: tuple[str, ...]
    published: tuple[date, date] | None
