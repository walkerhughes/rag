"""Checks that the evaluation contract in docs/evaluation/ stays internally consistent."""

import json
import tomllib
from pathlib import Path

CONTRACT = Path(__file__).parent.parent / "docs" / "evaluation"
REQUIRED = {"id", "split", "question_class", "question", "expected_evidence"}


def load_classes() -> dict[str, dict[str, object]]:
    with (CONTRACT / "classes.toml").open("rb") as f:
        classes: dict[str, dict[str, object]] = tomllib.load(f)["classes"]
    return classes


def load_examples() -> list[dict[str, object]]:
    text = (CONTRACT / "examples.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_every_example_matches_a_declared_class() -> None:
    classes = load_classes()
    examples = load_examples()

    ids = [e["id"] for e in examples]
    assert len(ids) == len(set(ids)), "duplicate example ids"

    for e in examples:
        assert e.keys() >= REQUIRED, f"{e['id']} is missing {REQUIRED - e.keys()}"
        assert e["question_class"] in classes, f"{e['id']} has an undeclared class"
        assert e["split"] in {"dev", "heldout"}, f"{e['id']} has an unknown split"


def test_every_class_has_both_splits() -> None:
    """No question class is claimed without both development and held-out examples."""
    examples = load_examples()
    for name in load_classes():
        splits = {e["split"] for e in examples if e["question_class"] == name}
        assert splits == {"dev", "heldout"}, f"{name} has only {splits or 'no examples'}"
