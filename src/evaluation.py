"""Packages the evaluation examples as Harbor Hub datasets.

`docs/evaluation/examples.jsonl` is the source of truth. Every example becomes a Harbor
task, and each split becomes a dataset directory that `harbor publish` accepts. The
packages are generated into an ignored directory rather than committed, so the examples
are never maintained in two formats and cannot disagree.

Publishing is a separate manual step. This writes files and reaches no network.
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "docs" / "evaluation" / "examples.jsonl"
OUTPUT = REPO / "dist" / "harbor"

# The Harbor organization that owns the published packages.
ORG = "walkerhughes"

# The task.toml schema version the harbor CLI writes as of this packaging.
SCHEMA_VERSION = "1.3"

# One dataset per split. The agent datasets named in the evaluation contract are absent
# on purpose: no agent loop exists to evaluate, and an empty dataset would claim one.
DATASETS = {"dev": "retrieval-dev", "heldout": "retrieval-heldout"}

# Task names share an organization namespace with everything else published there.
TASK_PREFIX = "retrieval-"

ANSWER_PATH = "/app/answer.json"

# Files a Harbor task package carries, in the shape `harbor publish` expects.
PACKAGE_FILES = ("task.toml", "instruction.md", "README.md")
PACKAGE_DIRS = ("environment", "tests", "solution")

DOCKERFILE = """\
# The verifier reads JSON, so the image needs an interpreter and nothing else. Corpus
# access is the responsibility of the agent under test, not of this image.
FROM python:3.13-slim

WORKDIR /app
"""

INSTRUCTION = """\
# Answer a question about the Dwarkesh Podcast archive

{question}

Write your answer to `{answer_path}` as a single JSON object:

```json
{{
  "answer": "<what the transcripts say, in prose>",
  "episodes": ["<episode slug>"],
  "speakers": ["<speaker name>"]
}}
```

`episodes` are the slugs of the episodes your answer rests on, as they appear in the
dwarkesh.com URL. `speakers` are the people who said what you are reporting. List every
episode and speaker the answer depends on, and no others. If the transcripts do not
answer the question, say so in `answer` and cite nothing.

The reward is how much of the annotated episode and speaker set your citations recover.
The prose answer must be present and non-empty; its wording is not scored.
"""

VERIFIER = '''\
"""Scores an answer against the episodes and speakers the example annotates."""

import json
import sys
from pathlib import Path

DEFAULT_ANSWER = Path("{answer_path}")
DEFAULT_EXPECTED = Path("/tests/expected.json")


def names(values: object) -> set[str]:
    """Comparable names, case and whitespace folded, from a JSON list of strings."""
    if not isinstance(values, list):
        return set()
    return {{str(value).strip().casefold() for value in values if str(value).strip()}}


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
    report = f"episode recall {{episodes:.2f}}, speaker recall {{speakers:.2f}}"
    return (episodes + speakers) / 2, report


def main(argv: list[str]) -> int:
    reward_path = Path(argv[1])
    answer_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_ANSWER
    expected_path = Path(argv[3]) if len(argv) > 3 else DEFAULT_EXPECTED

    expected = json.loads(expected_path.read_text())
    try:
        answer = json.loads(answer_path.read_text())
    except (OSError, ValueError) as error:
        reward, report = 0.0, f"no readable answer at {{answer_path}}: {{error}}"
    else:
        if isinstance(answer, dict):
            reward, report = score(answer, expected)
        else:
            reward, report = 0.0, f"the answer at {{answer_path}} is not a JSON object"

    reward_path.parent.mkdir(parents=True, exist_ok=True)
    reward_path.write_text(f"{{reward}}\\n")
    print(f"{{expected['id']}}: reward {{reward}} ({{report}})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''

TEST_SCRIPT = """\
#!/bin/bash
# Scores the agent's answer. A crashed verifier is a zero rather than a missing reward.
set -u

REWARD_DIR=/logs/verifier
mkdir -p "$REWARD_DIR"

if ! python3 /tests/verify.py "$REWARD_DIR/reward.txt"; then
    echo 0 > "$REWARD_DIR/reward.txt"
fi
"""

SOLVE_SCRIPT = """\
#!/bin/bash
# The oracle answer, so a run with the oracle agent proves the verifier scores a
# correct answer rather than proving only that the package builds.
set -euo pipefail

mkdir -p "$(dirname {answer_path})"
cp /solution/answer.json {answer_path}
"""

DATASET_README = """\
# {name}

Retrieval evaluation questions over the Dwarkesh Podcast archive, {split} split,
{count} tasks.

Generated from `docs/evaluation/examples.jsonl` by `make harbor-package`. The examples
are the source of truth and this package is disposable: regenerate it rather than
editing it.

Each task gives a question and asks for a prose answer plus the episodes and speakers it
rests on. The reward is the mean of episode recall and speaker recall against the
annotated citations, and zero when the prose answer is missing. An example that annotates
no episodes is one the corpus cannot answer, and there any citation scores zero. Answer
quality, groundedness, and latency are not scored here.

The task image ships no corpus. The dataset measures an agent that brings its own access
to the transcripts.
"""


def load_examples(path: Path) -> list[dict[str, Any]]:
    """Every example, in file order."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def toml_value(value: object) -> str:
    """A TOML literal. JSON string escaping is a subset of TOML basic string escaping."""
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def strings(value: object) -> list[str]:
    """A list of strings from an optional example field."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def short_name(example: dict[str, Any]) -> str:
    return f"{TASK_PREFIX}{example['id']}"


def write_script(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def task_config(example: dict[str, Any], org: str) -> str:
    """The task.toml, carrying the example's provenance in [metadata]."""
    keywords = ["dwarkesh", "retrieval", example["question_class"], example["split"]]
    lines = [
        f"schema_version = {toml_value(SCHEMA_VERSION)}",
        "",
        "[task]",
        f"name = {toml_value(f'{org}/{short_name(example)}')}",
        f"description = {toml_value(example['question'])}",
        "authors = []",
        f"keywords = {toml_value(keywords)}",
        "",
        "# Where this task came from, so a hub result resolves back to the example.",
        "[metadata]",
        'category = "retrieval"',
        f"example_id = {toml_value(example['id'])}",
        f"split = {toml_value(example['split'])}",
        f"question_class = {toml_value(example['question_class'])}",
        f"topics = {toml_value(strings(example.get('topics')))}",
        "",
        "[agent]",
        "timeout_sec = 600.0",
        "",
        "[verifier]",
        "timeout_sec = 120.0",
        "",
        "[environment]",
        "build_timeout_sec = 600.0",
        "",
    ]
    return "\n".join(lines)


def write_task(task_dir: Path, example: dict[str, Any], org: str) -> None:
    """One Harbor task package: the question, the environment, the verifier, the oracle."""
    for name in PACKAGE_DIRS:
        (task_dir / name).mkdir(parents=True, exist_ok=True)

    episodes = strings(example.get("expected_episodes"))
    speakers = strings(example.get("expected_speakers"))

    (task_dir / "task.toml").write_text(task_config(example, org))
    (task_dir / "instruction.md").write_text(
        INSTRUCTION.format(question=example["question"], answer_path=ANSWER_PATH)
    )
    (task_dir / "environment" / "Dockerfile").write_text(DOCKERFILE)

    (task_dir / "tests" / "expected.json").write_text(
        json.dumps(
            {"id": example["id"], "episodes": episodes, "speakers": speakers},
            indent=2,
        )
        + "\n"
    )
    (task_dir / "tests" / "verify.py").write_text(VERIFIER.format(answer_path=ANSWER_PATH))
    write_script(task_dir / "tests" / "test.sh", TEST_SCRIPT)

    (task_dir / "solution" / "answer.json").write_text(
        json.dumps(
            {
                "answer": example["expected_evidence"],
                "episodes": episodes,
                "speakers": speakers,
            },
            indent=2,
        )
        + "\n"
    )
    write_script(task_dir / "solution" / "solve.sh", SOLVE_SCRIPT.format(answer_path=ANSWER_PATH))


def content_digest(task_dir: Path) -> str:
    """The content hash Harbor pins a task reference to, over the package's files.

    Harbor hashes each publishable file, then hashes the sorted `path\\0hash` lines.
    `harbor sync` recomputes these with Harbor's own implementation.
    """
    files = [task_dir / name for name in PACKAGE_FILES if (task_dir / name).exists()]
    for name in PACKAGE_DIRS:
        files.extend(path for path in (task_dir / name).rglob("*") if path.is_file())

    outer = hashlib.sha256()
    for path in sorted(files, key=lambda path: path.relative_to(task_dir).as_posix()):
        inner = hashlib.sha256(path.read_bytes()).hexdigest()
        outer.update(f"{path.relative_to(task_dir).as_posix()}\0{inner}\n".encode())
    return f"sha256:{outer.hexdigest()}"


def dataset_manifest(name: str, split: str, tasks: list[tuple[str, str]], org: str) -> str:
    lines = [
        "# Generated from docs/evaluation/examples.jsonl by `make harbor-package`.",
        "# Regenerate rather than edit: the examples are the source of truth.",
        "",
        "[dataset]",
        f"name = {toml_value(f'{org}/{name}')}",
        f"description = {toml_value(f'Dwarkesh Podcast retrieval evaluation, {split} split.')}",
        "authors = []",
        f"keywords = {toml_value(['dwarkesh', 'retrieval', split])}",
    ]
    for task_name, digest in tasks:
        lines += [
            "",
            "[[tasks]]",
            f"name = {toml_value(f'{org}/{task_name}')}",
            f"digest = {toml_value(digest)}",
        ]
    return "\n".join(lines) + "\n"


def clear(dataset_dir: Path) -> None:
    """Removes a previous generation, refusing to touch a directory it did not write."""
    if not dataset_dir.exists():
        return
    if not (dataset_dir / "dataset.toml").exists():
        raise SystemExit(f"{dataset_dir} exists and is not a generated dataset")
    shutil.rmtree(dataset_dir)


def write_dataset(
    output: Path, split: str, examples: list[dict[str, Any]], org: str
) -> tuple[Path, int]:
    name = DATASETS[split]
    dataset_dir = output / name
    clear(dataset_dir)
    dataset_dir.mkdir(parents=True)

    tasks = []
    for example in examples:
        task_dir = dataset_dir / short_name(example)
        task_dir.mkdir()
        write_task(task_dir, example, org)
        tasks.append((short_name(example), content_digest(task_dir)))

    (dataset_dir / "dataset.toml").write_text(dataset_manifest(name, split, tasks, org))
    (dataset_dir / "README.md").write_text(
        DATASET_README.format(name=f"{org}/{name}", split=split, count=len(tasks))
    )
    return dataset_dir, len(tasks)


def generate(output: Path, examples: list[dict[str, Any]], org: str = ORG) -> list[Path]:
    """A publishable dataset directory per split, one task per example."""
    unknown = {example["split"] for example in examples} - set(DATASETS)
    if unknown:
        raise SystemExit(f"examples carry splits with no dataset: {sorted(unknown)}")

    written = []
    for split in DATASETS:
        members = [example for example in examples if example["split"] == split]
        dataset_dir, count = write_dataset(output, split, members, org)
        print(f"{dataset_dir}  {count} tasks")
        written.append(dataset_dir)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, default=EXAMPLES)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--org", default=ORG)
    args = parser.parse_args(argv)

    written = generate(args.out, load_examples(args.examples), args.org)
    paths = " ".join(str(path) for path in written)
    print(f"publish with: harbor publish {paths} --private")
    return 0


if __name__ == "__main__":
    sys.exit(main())
