"""Scores an answer against the episodes and speakers the example annotates."""

import json
import sys
from pathlib import Path

DEFAULT_ANSWER = Path("/app/answer.json")
DEFAULT_EXPECTED = Path("/tests/expected.json")


def names(values: object) -> set[str]:
    """Comparable names, case and whitespace folded, from a JSON list of strings."""
    if not isinstance(values, list):
        return set()
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def recall(cited: set[str], wanted: set[str]) -> float:
    """The share of the annotated set the answer recovered."""
    if not wanted:
        return 1.0
    return len(cited & wanted) / len(wanted)


def score(answer: dict[str, object], expected: dict[str, object]) -> tuple[float, str]:
    prose = answer.get("answer")
    if not isinstance(prose, str) or not prose.strip():
        return 0.0, "the answer field is missing or empty"

    cited_episodes = names(answer.get("episodes"))
    cited_speakers = names(answer.get("speakers"))
    wanted_episodes = names(expected.get("episodes"))
    wanted_speakers = names(expected.get("speakers"))

    # An example that annotates nothing is one the corpus cannot answer. The only
    # correct response cites nothing, so any citation is a fabrication.
    if not wanted_episodes and not wanted_speakers:
        if cited_episodes or cited_speakers:
            return 0.0, "nothing to cite, but the answer cites something"
        return 1.0, "nothing to cite, and the answer cites nothing"

    episodes = recall(cited_episodes, wanted_episodes)
    speakers = recall(cited_speakers, wanted_speakers)
    report = f"episode recall {episodes:.2f}, speaker recall {speakers:.2f}"
    return (episodes + speakers) / 2, report


def main(argv: list[str]) -> int:
    reward_path = Path(argv[1])
    answer_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_ANSWER
    expected_path = Path(argv[3]) if len(argv) > 3 else DEFAULT_EXPECTED

    expected = json.loads(expected_path.read_text())
    try:
        answer = json.loads(answer_path.read_text())
    except (OSError, ValueError) as error:
        reward, report = 0.0, f"no readable answer at {answer_path}: {error}"
    else:
        if isinstance(answer, dict):
            reward, report = score(answer, expected)
        else:
            reward, report = 0.0, f"the answer at {answer_path} is not a JSON object"

    reward_path.parent.mkdir(parents=True, exist_ok=True)
    reward_path.write_text(f"{reward}\n")
    print(f"{expected['id']}: reward {reward} ({report})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
