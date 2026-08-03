"""Reading the evaluation examples as retrieval ground truth.

`docs/evaluation/examples.jsonl` is one dataset serving two purposes. Retrieval scores
read `expected_phrases`, the verbatim snippets a correct retrieval must surface; the
agent fields are ignored here.

An example carrying no phrases is not scorable and is set aside by name rather than
scored zero, because a zero would read as a retrieval failure when it is a missing
annotation.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from evaluation import Example

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "docs/evaluation/examples.jsonl"
PHRASES = "expected_phrases"
SPLITS = ("dev", "heldout")


@dataclass(frozen=True)
class Dataset:
    """The scorable examples, and the identifiers of everything left out."""

    path: Path
    split: str
    examples: tuple[Example, ...]
    unannotated: tuple[str, ...]

    @property
    def origin(self) -> str:
        """The file the report names, relative to the repository when it lies inside it."""
        if self.path.is_relative_to(ROOT):
            return str(self.path.relative_to(ROOT))
        return str(self.path)


def _phrases(row: dict[str, object]) -> tuple[str, ...]:
    raw = row.get(PHRASES) or []
    if not isinstance(raw, list):
        raise ValueError(f"{row['id']}: {PHRASES} is not a list")
    return tuple(str(phrase) for phrase in raw)


def _rows(path: Path) -> Iterable[dict[str, object]]:
    for line in path.read_text().splitlines():
        if line.strip():
            row: dict[str, object] = json.loads(line)
            yield row


def load(path: Path = EXAMPLES, *, split: str | None = None) -> Dataset:
    """Every example in `split`, or in all splits when it is None.

    The held-out split is for release gates, so a report defaults to development
    examples and reaches the rest only when asked.
    """
    if split is not None and split not in SPLITS:
        raise ValueError(f"unknown split {split!r}, expected one of {', '.join(SPLITS)}")

    examples, unannotated = [], []
    for row in _rows(path):
        if split is not None and row.get("split") != split:
            continue
        phrases = _phrases(row)
        identifier = str(row["id"])
        if not phrases:
            unannotated.append(identifier)
            continue
        examples.append(
            Example(
                id=identifier,
                question_class=str(row["question_class"]),
                question=str(row["question"]),
                expected_phrases=phrases,
            )
        )
    return Dataset(
        path=path,
        split=split or "all",
        examples=tuple(examples),
        unannotated=tuple(unannotated),
    )
