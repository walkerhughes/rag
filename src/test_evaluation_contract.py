"""Checks that the evaluation contract in docs/evaluation/ stays internally consistent."""

import json
import tomllib
from itertools import permutations
from pathlib import Path

CONTRACT = Path(__file__).parent.parent / "docs" / "evaluation"
REQUIRED = {"id", "split", "question_class", "question", "expected_evidence", "expected_phrases"}

# Below this, recall over a class is too coarse to distinguish two retrieval configurations.
MINIMUM_PER_CLASS = 8

# A phrase has to name one passage. Measured over the ingested corpus of 1452 chunks, an
# excerpt of 20 characters is unique 97 percent of the time and one of 25 characters 99
# percent. Matching a phrase for real needs a database; this is the offline proxy.
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


def test_every_example_is_well_formed() -> None:
    """Identity, class membership, and the fields every example has to fill in.

    A repeated question is split leakage as soon as the two copies land in different splits.
    """
    classes = load_classes()
    examples = load_examples()

    for e in examples:
        assert e.keys() >= REQUIRED, f"{e['id']} is missing {REQUIRED - e.keys()}"
        assert all(e[key] for key in REQUIRED), f"{e['id']} leaves a required field empty"
        assert e["question_class"] in classes, f"{e['id']} has an undeclared class"
        assert e["split"] in {"dev", "heldout"}, f"{e['id']} has an unknown split"

    ids = [e["id"] for e in examples]
    assert len(ids) == len(set(ids)), "duplicate example ids"
    questions = [e["question"] for e in examples]
    assert len(questions) == len(set(questions)), "duplicate questions"


def test_every_class_is_measurable() -> None:
    """A class needs both splits and enough examples for recall over it to mean anything.

    Below the floor, recall takes so few values that no figure in classes.toml is
    measurable and no run separates two similar retrieval configurations.
    """
    examples = load_examples()
    for name in load_classes():
        of_class = [e for e in examples if e["question_class"] == name]
        splits = {e["split"] for e in of_class}
        assert splits == {"dev", "heldout"}, f"{name} has only {splits or 'no examples'}"
        assert len(of_class) >= MINIMUM_PER_CLASS, (
            f"{name} has {len(of_class)}, below {MINIMUM_PER_CLASS}"
        )


def test_every_referenced_episode_is_known_to_parse() -> None:
    """An example citing an unretrievable episode makes a dataset bug look like a regression."""
    parsed = load_parsed_episodes()
    for e in load_examples():
        unknown = sorted(set(episodes_of(e)) - parsed)
        assert not unknown, f"{e['id']} cites {unknown}, absent from episodes.toml"


def test_expected_phrases_are_usable_ground_truth() -> None:
    """Recall needs ground truth a harness can match, which prose evidence is not.

    One phrase per episode, since recall is measured over the set. The single phrase of
    slack covers an exchange where two speakers meet inside one episode. A phrase that
    contains another counts the same passage twice, and two examples sharing a whole
    phrase set are one example scored twice.

    Phrases match byte for byte and the transcripts mix curly and straight apostrophes, so
    nothing offline distinguishes a correct phrase from one whose quotes were straightened.
    Only running the phrases against the corpus catches that.
    """
    owner_of: dict[tuple[str, ...], str] = {}
    for e in load_examples():
        phrases = phrases_of(e)
        for phrase in phrases:
            assert phrase == phrase.strip(), f"{e['id']} has a phrase with edge whitespace"
            assert len(phrase) >= MINIMUM_PHRASE_CHARS, f"{e['id']} has a short phrase: {phrase!r}"
        for shorter, longer in permutations(phrases, 2):
            assert shorter not in longer, f"{e['id']} repeats or contains a phrase: {shorter!r}"

        episodes = max(len(set(episodes_of(e))), 1)
        assert len(phrases) >= episodes, f"{e['id']} needs {episodes} phrases, has {len(phrases)}"
        assert len(phrases) <= episodes + 1, f"{e['id']} has {len(phrases)} phrases, padded"

        key = tuple(sorted(phrases))
        assert key not in owner_of, f"{e['id']} has the same phrase set as {owner_of.get(key)}"
        owner_of[key] = str(e["id"])
