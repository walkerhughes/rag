"""Full-text search over chunks.

Postgres maintains the search vector as a generated column, so the index cannot drift
from the text. Ranking uses ts_rank_cd, and ties break on chunk id so that repeating a
query returns the same order.
"""

from datetime import date

from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.orm import Session

from observability import tracer
from retrieval import Evidence
from storage.postgres import models

STRATEGY = "lexical"
DEFAULT_LIMIT = 10


def _any_term(query: str) -> ColumnElement[object]:
    """A query matching passages that contain any of the question's terms.

    plainto_tsquery requires every term, which makes a natural-language question
    unmatchable: a nine-word question finds nothing. Reducing the question to its lexemes
    and joining them with OR lets ts_rank_cd sort by how many terms a passage covers.

    nullif keeps a question of nothing but stopwords from reaching to_tsquery, which
    rejects an empty string. A null query matches no rows, which is the right answer.
    """
    lexemes = func.tsvector_to_array(func.to_tsvector("english", query))
    return func.to_tsquery("english", func.nullif(func.array_to_string(lexemes, " | "), ""))


def _filtered(
    statement: Select[tuple[models.Chunk, models.Episode, float]],
    episodes: list[str] | None,
    speakers: list[str] | None,
    published_after: date | None,
    published_before: date | None,
) -> Select[tuple[models.Chunk, models.Episode, float]]:
    conditions: list[ColumnElement[bool]] = []
    if episodes:
        conditions.append(models.Episode.source_id.in_(episodes))
    if speakers:
        conditions.append(models.Chunk.speakers.overlap(speakers))
    if published_after:
        conditions.append(models.Episode.published_at >= published_after)
    if published_before:
        conditions.append(models.Episode.published_at <= published_before)
    return statement.where(and_(*conditions)) if conditions else statement


def search(
    session: Session,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    episodes: list[str] | None = None,
    speakers: list[str] | None = None,
    published_after: date | None = None,
    published_before: date | None = None,
) -> list[Evidence]:
    """Ranked passages matching `query`, narrowed by any filters given."""
    with tracer.start_as_current_span("retrieval.lexical") as span:
        span.set_attribute("retrieval.limit", limit)
        span.set_attribute("retrieval.filtered", bool(episodes or speakers))

        tsquery = _any_term(query)
        rank = func.ts_rank_cd(models.Chunk.search, tsquery).label("score")

        statement = (
            select(models.Chunk, models.Episode, rank)
            .join(models.Episode, models.Chunk.episode_id == models.Episode.id)
            .where(models.Chunk.search.op("@@")(tsquery))
        )
        statement = _filtered(statement, episodes, speakers, published_after, published_before)
        # Ties break on where a passage sits, not on its identifier: identifiers are
        # generated per ingest, so ranking on them changes when the same transcripts are
        # ingested again. ts_rank_cd ties often, which makes this the common path.
        statement = statement.order_by(
            rank.desc(), models.Episode.source_id, models.Chunk.ordinal
        ).limit(limit)

        results = [
            Evidence(
                chunk_id=chunk.id,
                episode_source_id=episode.source_id,
                episode_title=episode.title,
                published_at=episode.published_at,
                speakers=list(chunk.speakers),
                text=chunk.text,
                first_position=chunk.first_position,
                last_position=chunk.last_position,
                start=chunk.start,
                score=float(score),
                strategy=STRATEGY,
            )
            for chunk, episode, score in session.execute(statement).all()
        ]
        span.set_attribute("retrieval.results", len(results))
        return results
