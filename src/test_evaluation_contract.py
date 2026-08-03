"""Checks that the evaluation contract in docs/evaluation/ stays internally consistent."""

import json
import tomllib
from pathlib import Path

CONTRACT = Path(__file__).parent.parent / "docs" / "evaluation"
REQUIRED = {"id", "split", "question_class", "question", "expected_evidence", "expected_phrases"}

# Below this, recall over a class is too coarse to distinguish two retrieval configurations.
MINIMUM_PER_CLASS = 8

# Shorter than this, a phrase matches passages the example never meant. Grounding a phrase
# in the corpus needs a database and happens outside CI; this is the offline proxy.
MINIMUM_PHRASE_CHARS = 25


def load_classes() -> dict[str, dict[str, object]]:
    with (CONTRACT / "classes.toml").open("rb") as f:
        classes: dict[str, dict[str, object]] = tomllib.load(f)["classes"]
    return classes


def load_parsed_episodes() -> set[str]:
    with (CONTRACT / "episodes.toml").open("rb") as f:
        parsed: list[str] = tomllib.load(f)["parsed"]
    return set(parsed)


def load_examples() -> list[dict[str, object]]:
    text = (CONTRACT / "examples.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def episodes_of(example: dict[str, object]) -> list[str]:
    """The slugs an example depends on. Absent or empty for a deliberately unanchored one."""
    slugs = example.get("expected_episodes", [])
    assert isinstance(slugs, list), f"{example['id']} has a non-list expected_episodes"
    return [str(slug) for slug in slugs]


def phrases_of(example: dict[str, object]) -> list[str]:
    """The verbatim transcript snippets a correct answer has to cite."""
    phrases = example.get("expected_phrases")
    assert isinstance(phrases, list), f"{example['id']} has a non-list expected_phrases"
    return [str(phrase) for phrase in phrases]


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


def test_every_class_has_enough_examples() -> None:
    """A class thin enough that recall can only be 0, 0.5 or 1.0 measures nothing."""
    examples = load_examples()
    for name in load_classes():
        count = sum(1 for e in examples if e["question_class"] == name)
        assert count >= MINIMUM_PER_CLASS, f"{name} has {count}, below {MINIMUM_PER_CLASS}"


def test_every_referenced_episode_is_known_to_parse() -> None:
    """An example citing an unretrievable episode makes a dataset bug look like a regression."""
    parsed = load_parsed_episodes()
    for e in load_examples():
        unknown = sorted(set(episodes_of(e)) - parsed)
        assert not unknown, f"{e['id']} cites {unknown}, absent from episodes.toml"


def test_every_example_carries_usable_phrases() -> None:
    """Recall needs ground truth a harness can match, which prose evidence is not."""
    for e in load_examples():
        phrases = phrases_of(e)
        assert phrases, f"{e['id']} has no expected_phrases"
        assert len(set(phrases)) == len(phrases), f"{e['id']} repeats a phrase"
        for phrase in phrases:
            assert phrase == phrase.strip(), f"{e['id']} has a phrase with edge whitespace"
            assert len(phrase) >= MINIMUM_PHRASE_CHARS, f"{e['id']} has a short phrase: {phrase!r}"


def test_phrase_count_matches_the_episodes_an_example_depends_on() -> None:
    """Recall is measured over the set, so a question spanning episodes needs one per episode.

    The single slack phrase covers an exchange where two speakers meet in one episode.
    """
    for e in load_examples():
        episodes = len(set(episodes_of(e)))
        phrases = len(phrases_of(e))
        assert phrases >= episodes, f"{e['id']} names {episodes} episodes but {phrases} phrases"
        assert phrases <= max(episodes, 1) + 1, f"{e['id']} has {phrases} phrases, padded"
