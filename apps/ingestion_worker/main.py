"""Command line entry point for corpus ingestion."""

import argparse
import sys
import textwrap
from collections.abc import Sequence

from corpus.ingestion.dwarkesh import client, pipeline
from corpus.models import Episode
from observability import configure_tracing, tracer
from retrieval.indexing import index_all, index_episode
from storage.postgres import session

ARCHIVE_SEARCH_DEPTH = 200
EXCERPT = 100


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


def describe(episode: Episode) -> str:
    """What a parse looks like, in enough detail to tell a good one from a bad one."""
    segments = episode.segments
    words = sum(len(segment.text.split()) for segment in segments)
    timed = sum(1 for segment in segments if segment.start is not None)
    longest = max(segments, key=lambda segment: len(segment.text))

    return "\n".join(
        [
            f"{episode.source_id}  {episode.published_at}",
            f"  title      {episode.title}",
            f"  turns      {len(segments)}",
            f"  speakers   {', '.join(episode.speakers)}",
            f"  words      {words}",
            f"  timestamps {timed}/{len(segments)}",
            f"  longest    {len(longest.text)} chars, {longest.speaker}",
            f"  first      {segments[0].speaker}: {textwrap.shorten(segments[0].text, EXCERPT)}",
            f"  last       {segments[-1].speaker}: {textwrap.shorten(segments[-1].text, EXCERPT)}",
        ]
    )


def dry_run(listings: list[client.EpisodeListing]) -> int:
    """Fetches and parses without writing, so a parse can be checked before a full run."""
    failures = 0
    for listing in listings:
        try:
            print(describe(pipeline.fetch_and_parse(listing)))
        except pipeline.QUARANTINABLE as error:
            failures += 1
            print(f"{listing.slug}  FAILED  {type(error).__name__}: {error}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = argparse.ArgumentParser(description="Ingest Dwarkesh episodes into the corpus.")
    arguments.add_argument("--limit", type=int, default=5, help="how many recent episodes")
    arguments.add_argument("--slug", action="append", help="ingest one episode; repeatable")
    arguments.add_argument(
        "--reindex",
        action="store_true",
        help="re-chunk every stored episode, fetching nothing",
    )
    arguments.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and parse only, writing nothing and needing no database",
    )
    parsed = arguments.parse_args(argv)

    configure_tracing("rag-ingestion")
    with tracer.start_as_current_span("ingestion_worker") as span:
        span.set_attribute("ingestion.dry_run", parsed.dry_run)

        if parsed.reindex:
            with session() as active:
                chunks = index_all(active)
            print(f"re-chunked {chunks} chunks")
            return 0

        listings = select(parsed.limit, parsed.slug)

        if parsed.dry_run:
            return dry_run(listings)

        with session() as active:
            result = pipeline.ingest(active, listings)
            # Chunking is a separate step: ingestion writes documents and knows nothing
            # about retrieval. The two are joined here, at the entry point.
            for episode_id in result.episode_ids:
                index_episode(active, episode_id)

    print(result.summary)
    for slug, reason in result.quarantined.items():
        print(f"  quarantined {slug}: {reason}", file=sys.stderr)
    # Nothing ingested means the run achieved nothing, whatever the reason.
    return 0 if result.ingested else 1


if __name__ == "__main__":
    raise SystemExit(main())
