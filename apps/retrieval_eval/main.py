"""Command line entry point for the retrieval evaluation report.

Measures whatever corpus the local database holds. The regression gate builds its own
corpus from committed fixtures because a gate whose corpus moves measures the corpus; a
baseline report has the opposite need, which is the real archive, and there is no honest
way to carry fourteen episodes into CI. The corpus is therefore described in the report
rather than fixed, so a number can never be mistaken for one taken on a different corpus.

No tracing is configured. A report a developer runs is not a service, and giving it a
Honeycomb dataset would spend events on a local run.
"""

import argparse
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evaluation import Corpus
from evaluation.dataset import EXAMPLES, load
from evaluation.harness import DEFAULT_K, measure, render
from retrieval import Search, bm25, lexical
from storage.postgres import models, session


def fingerprint(active: Session) -> Corpus:
    """What is in the database right now, in enough detail to identify the corpus."""
    episodes = (
        active.execute(select(models.Episode.source_id).order_by(models.Episode.source_id))
        .scalars()
        .all()
    )
    turns = active.execute(select(func.count()).select_from(models.TranscriptSegment)).scalar_one()
    chunks = active.execute(select(func.count()).select_from(models.Chunk)).scalar_one()
    versions = (
        active.execute(select(models.Chunk.chunker_version).distinct().order_by("chunker_version"))
        .scalars()
        .all()
    )
    window = active.execute(
        select(func.min(models.Episode.published_at), func.max(models.Episode.published_at))
    ).one()

    return Corpus(
        label="the local database, whatever has been ingested into it",
        episodes=tuple(episodes),
        turns=turns,
        chunks=chunks,
        chunker_versions=tuple(versions),
        published=(window[0], window[1]) if window[0] else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = argparse.ArgumentParser(
        description="Measure retrieval precision and recall against the ingested corpus."
    )
    arguments.add_argument(
        "--split",
        choices=("dev", "heldout", "all"),
        default="dev",
        help="which examples to score; held-out examples are for release gates",
    )
    arguments.add_argument(
        "--examples",
        type=Path,
        default=EXAMPLES,
        help="an example file to score, for checking an annotation before committing it",
    )
    arguments.add_argument(
        "--k",
        type=int,
        action="append",
        help=f"a rank to score at; repeatable, defaults to {', '.join(map(str, DEFAULT_K))}",
    )
    parsed = arguments.parse_args(argv)
    ks = tuple(sorted(set(parsed.k))) if parsed.k else DEFAULT_K

    dataset = load(parsed.examples, split=None if parsed.split == "all" else parsed.split)

    with session() as active:
        corpus = fingerprint(active)
        if not corpus.chunks:
            raise SystemExit("the database holds no chunks: run `make ingest` before measuring")
        searches: dict[str, Search] = {
            lexical.STRATEGY: partial(lexical.search, active),
            bm25.STRATEGY: partial(bm25.search, bm25.client()),
        }
        scores = measure(searches, dataset.examples, ks)

    print(render(corpus, dataset, scores))
    # An unscorable dataset is a failure of the run, not a result of zero.
    return 0 if dataset.examples else 1


if __name__ == "__main__":
    raise SystemExit(main())
