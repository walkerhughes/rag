"""Reading the evaluation examples as retrieval ground truth.

`docs/evaluation/examples.jsonl` is one dataset serving two purposes. Retrieval scores
read `expected_phrases`, the verbatim snippets a correct retrieval must surface; the
agent fields are ignored here.

An example carrying no phrases is not scorable and is set aside by name rather than
scored zero, because a zero would read as a retrieval failure when it is a missing
annotation.
"""

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "docs/evaluation/examples.jsonl"
SPLITS = ("dev", "heldout")


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


def load(path: Path = EXAMPLES, *, split: str | None = None) -> Dataset:
    """Every example in `split`, or in all splits when it is None.

    The held-out split is for release gates, so a report defaults to development
    examples and reaches the rest only when asked.
    """
    if split is not None and split not in SPLITS:
        raise ValueError(f"unknown split {split!r}, expected one of {', '.join(SPLITS)}")

    examples, unannotated = [], []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row: dict[str, object] = json.loads(line)
        if split is not None and row.get("split") != split:
            continue
        phrases = row.get("expected_phrases") or []
        if not isinstance(phrases, list):
            raise ValueError(f"{row['id']}: expected_phrases is not a list")
        identifier = str(row["id"])
        if not phrases:
            unannotated.append(identifier)
            continue
        examples.append(
            Example(
                id=identifier,
                question_class=str(row["question_class"]),
                question=str(row["question"]),
                expected_phrases=tuple(str(phrase) for phrase in phrases),
            )
        )
    return Dataset(
        path=path,
        split=split or "all",
        examples=tuple(examples),
        unannotated=tuple(unannotated),
    )
