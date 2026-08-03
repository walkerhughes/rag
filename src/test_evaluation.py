"""Checks that the generated Harbor packaging is publishable and loses no example."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

import evaluation

ORG = "test-org"


@pytest.fixture(scope="module")
def examples() -> list[dict[str, Any]]:
    return evaluation.load_examples(evaluation.EXAMPLES)


@pytest.fixture(scope="module")
def packaged(tmp_path_factory: pytest.TempPathFactory, examples: list[dict[str, Any]]) -> Path:
    output = tmp_path_factory.mktemp("harbor")
    evaluation.generate(output, examples, ORG)
    return output


def manifest(dataset_dir: Path) -> dict[str, Any]:
    with (dataset_dir / "dataset.toml").open("rb") as f:
        loaded: dict[str, Any] = tomllib.load(f)
    return loaded


def test_every_example_reaches_exactly_one_dataset(
    packaged: Path, examples: list[dict[str, Any]]
) -> None:
    listed = [
        task["name"]
        for name in evaluation.DATASETS.values()
        for task in manifest(packaged / name)["tasks"]
    ]
    expected = [f"{ORG}/{evaluation.short_name(example)}" for example in examples]

    assert len(listed) == len(set(listed)), "a task is listed in both datasets"
    assert sorted(listed) == sorted(expected)


def test_the_split_partition_loses_nothing(packaged: Path, examples: list[dict[str, Any]]) -> None:
    for split, name in evaluation.DATASETS.items():
        wanted = {example["id"] for example in examples if example["split"] == split}
        packaged_ids = {
            json.loads((task_dir / "tests" / "expected.json").read_text())["id"]
            for task_dir in (packaged / name).iterdir()
            if task_dir.is_dir()
        }
        assert packaged_ids == wanted, f"{name} does not hold exactly the {split} examples"


def test_only_the_retrieval_datasets_are_packaged(packaged: Path) -> None:
    """No agent dataset: there is no agent loop, and an empty dataset would claim one."""
    assert sorted(path.name for path in packaged.iterdir()) == sorted(evaluation.DATASETS.values())


def test_each_dataset_manifest_matches_the_schema(packaged: Path) -> None:
    for split, name in evaluation.DATASETS.items():
        loaded = manifest(packaged / name)
        assert loaded["dataset"]["name"] == f"{ORG}/{name}"
        assert loaded["dataset"]["description"]
        assert split in loaded["dataset"]["keywords"]
        assert (packaged / name / "README.md").read_text()

        for task in loaded["tasks"]:
            assert task["name"].startswith(f"{ORG}/{evaluation.TASK_PREFIX}")
            assert task["digest"].startswith("sha256:")
            assert len(task["digest"]) == len("sha256:") + 64


def test_each_task_carries_what_harbor_requires(packaged: Path) -> None:
    for name in evaluation.DATASETS.values():
        for task in manifest(packaged / name)["tasks"]:
            task_dir = packaged / name / task["name"].split("/")[1]
            for required in ("instruction.md", "environment/Dockerfile", "tests/test.sh"):
                assert (task_dir / required).is_file(), f"{task_dir} is missing {required}"

            with (task_dir / "task.toml").open("rb") as f:
                config = tomllib.load(f)
            assert config["task"]["name"] == task["name"]
            assert config["task"]["description"]
            assert config["metadata"]["example_id"] in task["name"]
            assert (task_dir / "instruction.md").read_text().count(config["task"]["description"]), (
                "the instruction does not ask the question"
            )


def test_a_pinned_digest_matches_the_package_it_pins(packaged: Path) -> None:
    """A digest that has drifted from the files points the hub at nothing."""
    for name in evaluation.DATASETS.values():
        for task in manifest(packaged / name)["tasks"]:
            task_dir = packaged / name / task["name"].split("/")[1]
            assert evaluation.content_digest(task_dir) == task["digest"]


def test_regenerating_replaces_a_previous_generation(
    packaged: Path, examples: list[dict[str, Any]]
) -> None:
    before = manifest(packaged / evaluation.DATASETS["dev"])
    evaluation.generate(packaged, examples, ORG)
    assert manifest(packaged / evaluation.DATASETS["dev"]) == before


def test_generation_refuses_to_clobber_a_directory_it_did_not_write(
    tmp_path: Path, examples: list[dict[str, Any]]
) -> None:
    occupied = tmp_path / evaluation.DATASETS["dev"]
    occupied.mkdir(parents=True)
    (occupied / "notes.txt").write_text("something else")

    with pytest.raises(SystemExit):
        evaluation.generate(tmp_path, examples, ORG)
    assert (occupied / "notes.txt").exists()


def run_verifier(task_dir: Path, answer: Path, reward: Path) -> str:
    subprocess.run(
        [
            sys.executable,
            str(task_dir / "tests" / "verify.py"),
            str(reward),
            str(answer),
            str(task_dir / "tests" / "expected.json"),
        ],
        check=True,
        capture_output=True,
    )
    return reward.read_text().strip()


def first_task(packaged: Path) -> Path:
    dataset_dir = packaged / evaluation.DATASETS["dev"]
    task = str(manifest(dataset_dir)["tasks"][0]["name"]).split("/")[1]
    return dataset_dir / task


def test_the_verifier_scores_the_oracle_answer_full_marks(packaged: Path, tmp_path: Path) -> None:
    task_dir = first_task(packaged)
    reward = run_verifier(task_dir, task_dir / "solution" / "answer.json", tmp_path / "reward.txt")
    assert float(reward) == 1.0


def test_the_verifier_scores_a_wrong_answer_zero(packaged: Path, tmp_path: Path) -> None:
    task_dir = first_task(packaged)
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"answer": "a guess", "episodes": ["nobody"], "speakers": []}))

    reward = run_verifier(task_dir, answer, tmp_path / "reward.txt")
    assert float(reward) == 0.0


def test_the_verifier_scores_a_missing_answer_zero(packaged: Path, tmp_path: Path) -> None:
    task_dir = first_task(packaged)
    reward = run_verifier(task_dir, tmp_path / "absent.json", tmp_path / "reward.txt")
    assert float(reward) == 0.0


def unanchored(packaged: Path, tmp_path: Path) -> Path:
    """A task whose example annotates nothing, which the corpus cannot answer."""
    task_dir = tmp_path / "unanchored"
    (task_dir / "tests").mkdir(parents=True)
    verifier = first_task(packaged) / "tests" / "verify.py"
    (task_dir / "tests" / "verify.py").write_text(verifier.read_text())
    (task_dir / "tests" / "expected.json").write_text(
        json.dumps({"id": "unanchored-001", "episodes": [], "speakers": []})
    )
    return task_dir


def test_an_unanchored_example_rewards_citing_nothing(packaged: Path, tmp_path: Path) -> None:
    task_dir = unanchored(packaged, tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"answer": "the transcripts do not say"}))

    reward = run_verifier(task_dir, answer, tmp_path / "reward.txt")
    assert float(reward) == 1.0


def test_an_unanchored_example_rewards_a_fabricated_citation_zero(
    packaged: Path, tmp_path: Path
) -> None:
    task_dir = unanchored(packaged, tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"answer": "invented", "episodes": ["richard-sutton"]}))

    reward = run_verifier(task_dir, answer, tmp_path / "reward.txt")
    assert float(reward) == 0.0
