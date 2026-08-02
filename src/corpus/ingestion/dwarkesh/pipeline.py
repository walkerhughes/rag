"""Ingesting Dwarkesh episodes into the canonical corpus.

Each episode is written inside its own savepoint, so one unusable page neither aborts the
run nor leaves a half-written episode behind. Pages that cannot be fetched, parsed, or
validated are quarantined: the reason is recorded on the run and the episode is skipped.
"""

import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from corpus.ingestion.dwarkesh import client, parser
from corpus.models import Episode, IngestionStatus
from observability import tracer
from retrieval.indexing import index_episode
from storage.postgres import models, repositories

SOURCE = "dwarkesh"

# A page can fail in three ways that are the source's fault rather than ours.
QUARANTINABLE = (client.FetchError, parser.ParseError, ValidationError)


@dataclass
class Result:
    ingested: list[str] = field(default_factory=list)
    quarantined: dict[str, str] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        parts = [f"ingested {len(self.ingested)}"]
        if self.quarantined:
            reasons = "; ".join(f"{slug}: {why}" for slug, why in self.quarantined.items())
            parts.append(f"quarantined {len(self.quarantined)} ({reasons})")
        return ", ".join(parts)


def fetch_and_parse(listing: client.EpisodeListing) -> Episode:
    """Everything up to persistence. Touches no database, so it is safe to run anywhere."""
    with tracer.start_as_current_span("episode.fetch") as span:
        span.set_attribute("episode.source_id", listing.slug)
        html = client.fetch_page(listing.slug)
        span.set_attribute("episode.page_bytes", len(html))

    with tracer.start_as_current_span("episode.parse") as span:
        segments = parser.parse_transcript(html)
        span.set_attribute("episode.segments", len(segments))

    with tracer.start_as_current_span("episode.validate") as span:
        episode = Episode(
            source_id=listing.slug,
            title=listing.title,
            url=listing.url,
            published_at=listing.published_at,
            segments=segments,
        )
        span.set_attribute("episode.speakers", len(episode.speakers))
        return episode


def ingest_episode(
    session: Session, run: models.IngestionRun, listing: client.EpisodeListing
) -> uuid.UUID:
    episode = fetch_and_parse(listing)
    with tracer.start_as_current_span("episode.persist") as span:
        episode_id = repositories.save_episode(session, run, episode)
        span.set_attribute("episode.id", str(episode_id))

    index_episode(session, episode_id)
    return episode_id


def ingest(session: Session, listings: list[client.EpisodeListing]) -> Result:
    """Runs one ingestion run over the given episodes. The caller commits."""
    result = Result()
    run = repositories.start_run(session, SOURCE)

    with tracer.start_as_current_span("ingest.run") as span:
        span.set_attribute("ingestion.run_id", str(run.id))
        span.set_attribute("ingestion.requested", len(listings))

        for listing in listings:
            try:
                with session.begin_nested():
                    ingest_episode(session, run, listing)
            except QUARANTINABLE as error:
                reason = f"{type(error).__name__}: {error}"
                result.quarantined[listing.slug] = reason
                span.add_event(
                    "episode.quarantined",
                    {"episode.source_id": listing.slug, "reason": reason},
                )
            else:
                result.ingested.append(listing.slug)

        span.set_attribute("ingestion.ingested", len(result.ingested))
        span.set_attribute("ingestion.quarantined", len(result.quarantined))

        status = IngestionStatus.SUCCEEDED if result.ingested else IngestionStatus.FAILED
        repositories.finish_run(
            session, run, status, error=result.summary if result.quarantined else None
        )

    return result
