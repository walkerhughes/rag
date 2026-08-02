"""Command line entry point for corpus ingestion."""

import argparse
import sys
from collections.abc import Sequence

from corpus.ingestion.dwarkesh import client
from corpus.ingestion.dwarkesh.pipeline import ingest
from observability import configure_tracing, tracer
from storage.postgres import session

ARCHIVE_SEARCH_DEPTH = 120


def select(limit: int, slugs: list[str] | None) -> list[client.EpisodeListing]:
    if not slugs:
        return client.list_episodes(limit=limit)
    wanted = set(slugs)
    found = [
        listing
        for listing in client.list_episodes(limit=ARCHIVE_SEARCH_DEPTH)
        if listing.slug in wanted
    ]
    missing = wanted - {listing.slug for listing in found}
    if missing:
        raise SystemExit(f"not found in the archive: {', '.join(sorted(missing))}")
    return found


def main(argv: Sequence[str] | None = None) -> int:
    arguments = argparse.ArgumentParser(description="Ingest Dwarkesh episodes into the corpus.")
    arguments.add_argument("--limit", type=int, default=5, help="how many recent episodes")
    arguments.add_argument("--slug", action="append", help="ingest one episode; repeatable")
    parsed = arguments.parse_args(argv)

    configure_tracing("rag-ingestion")
    with tracer.start_as_current_span("ingestion_worker"):
        listings = select(parsed.limit, parsed.slug)
        with session() as active:
            result = ingest(active, listings)

    print(result.summary)
    for slug, reason in result.quarantined.items():
        print(f"  quarantined {slug}: {reason}", file=sys.stderr)
    # Nothing ingested means the run achieved nothing, whatever the reason.
    return 0 if result.ingested else 1


if __name__ == "__main__":
    raise SystemExit(main())
