"""Loading examples, including from a file that does not annotate every one.

Written against synthetic lines rather than the committed examples, so the tests measure
the loader rather than whatever the dataset happens to hold today.
"""

import json
from pathlib import Path

import pytest

from evaluation.dataset import EXAMPLES, Dataset, load

ROWS: list[dict[str, object]] = [
    {
        "id": "direct-001",
        "split": "dev",
        "question_class": "direct_retrieval",
        "question": "Where does the information go?",
        "expected_phrases": ["goes into the weights"],
    },
    {
        "id": "direct-002",
        "split": "heldout",
        "question_class": "direct_retrieval",
        "question": "What is the bitter lesson?",
        "expected_phrases": ["bitter lesson", "search and learning"],
    },
    {
        "id": "hop-001",
        "split": "dev",
        "question_class": "bounded_multi_hop",
        "question": "Who taught whom?",
    },
]


@pytest.fixture
def examples(tmp_path: Path) -> Path:
    path = tmp_path / "examples.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in ROWS) + "\n\n")
    return path


def test_a_split_selects_its_own_examples(examples: Path) -> None:
    assert [example.id for example in load(examples, split="dev").examples] == ["direct-001"]
    assert [example.id for example in load(examples, split="heldout").examples] == ["direct-002"]
    assert [example.id for example in load(examples).examples] == ["direct-001", "direct-002"]


def test_an_unannotated_example_is_named_rather_than_scored(examples: Path) -> None:
    """A missing annotation is a gap in the dataset, not a retrieval failure."""
    dataset = load(examples)
    assert dataset.unannotated == ("hop-001",)
    assert "hop-001" not in {example.id for example in dataset.examples}


def test_phrases_survive_loading(examples: Path) -> None:
    dataset = load(examples, split="heldout")
    assert dataset.examples[0].expected_phrases == ("bitter lesson", "search and learning")
    assert dataset.examples[0].question_class == "direct_retrieval"


def test_an_unknown_split_is_refused(examples: Path) -> None:
    with pytest.raises(ValueError, match="unknown split"):
        load(examples, split="train")


def test_a_malformed_annotation_is_not_quietly_dropped(tmp_path: Path) -> None:
    path = tmp_path / "examples.jsonl"
    path.write_text(json.dumps({**ROWS[0], "expected_phrases": "goes into the weights"}))
    with pytest.raises(ValueError, match="not a list"):
        load(path)


def test_the_committed_examples_load() -> None:
    """The dataset on disk stays readable, whether or not it is annotated yet."""
    dataset = load(EXAMPLES)
    assert isinstance(dataset, Dataset)
    lines = [line for line in EXAMPLES.read_text().splitlines() if line.strip()]
    assert len(dataset.examples) + len(dataset.unannotated) == len(lines)
