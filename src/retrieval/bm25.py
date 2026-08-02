"""BM25 search over chunks, using OpenSearch.

Postgres full-text ranking has no term-rarity weighting, so a common word counts as much
as a distinctive one. BM25 weights rare terms higher, which is the standard lexical
baseline and the reason this exists alongside the Postgres implementation.

The index is a projection of the chunk table. Postgres stays canonical, and the index can
be dropped and rebuilt from it at any time.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk

from config import settings
from observability import tracer
from retrieval import Evidence

STRATEGY = "bm25"
INDEX = "chunks"
DEFAULT_LIMIT = 10

# `english` stems and drops stopwords, matching what Postgres does to its search vector,
# so the two strategies differ on ranking rather than on tokenisation.
MAPPING: dict[str, Any] = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        "properties": {
            "text": {"type": "text", "analyzer": "english"},
            "episode_source_id": {"type": "keyword"},
            "episode_title": {"type": "keyword"},
            "speakers": {"type": "keyword"},
            "published_at": {"type": "date"},
            "first_position": {"type": "integer"},
            "last_position": {"type": "integer"},
            "start_seconds": {"type": "float"},
        }
    },
}


def client() -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url], timeout=30)


def ensure_index(search: OpenSearch) -> None:
    if not search.indices.exists(index=INDEX):
        search.indices.create(index=INDEX, body=MAPPING)


def recreate_index(search: OpenSearch) -> None:
    """Drops and rebuilds the index. Safe, because Postgres holds the chunks."""
    search.indices.delete(index=INDEX, ignore_unavailable=True)
    search.indices.create(index=INDEX, body=MAPPING)


def index_documents(search: OpenSearch, documents: list[dict[str, Any]]) -> int:
    """Writes chunk documents. The chunk identifier is the document identifier."""
    if not documents:
        return 0
    with tracer.start_as_current_span("bm25.index") as span:
        span.set_attribute("bm25.documents", len(documents))
        actions = [
            {"_index": INDEX, "_id": document.pop("chunk_id"), "_source": document}
            for document in documents
        ]
        written, _ = bulk(search, actions, refresh=True)
        return int(written)


def _filters(
    episodes: list[str] | None,
    speakers: list[str] | None,
    published_after: date | None,
    published_before: date | None,
) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if episodes:
        clauses.append({"terms": {"episode_source_id": episodes}})
    if speakers:
        clauses.append({"terms": {"speakers": speakers}})
    if published_after or published_before:
        window: dict[str, str] = {}
        if published_after:
            window["gte"] = published_after.isoformat()
        if published_before:
            window["lte"] = published_before.isoformat()
        clauses.append({"range": {"published_at": window}})
    return clauses


def search_chunks(
    search: OpenSearch,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    episodes: list[str] | None = None,
    speakers: list[str] | None = None,
    published_after: date | None = None,
    published_before: date | None = None,
) -> list[Evidence]:
    """Ranked passages matching `query`, narrowed by any filters given."""
    with tracer.start_as_current_span("retrieval.bm25") as span:
        span.set_attribute("retrieval.limit", limit)
        span.set_attribute("retrieval.filtered", bool(episodes or speakers))

        if not query.strip():
            return []

        body: dict[str, Any] = {
            "size": limit,
            "query": {
                "bool": {
                    "must": [{"match": {"text": query}}],
                    "filter": _filters(episodes, speakers, published_after, published_before),
                }
            },
            # Ties break on identifier, so repeating a query returns the same order.
            "sort": ["_score", {"_id": "asc"}],
        }
        hits = search.search(index=INDEX, body=body)["hits"]["hits"]

        results = [
            Evidence(
                chunk_id=uuid.UUID(hit["_id"]),
                episode_source_id=hit["_source"]["episode_source_id"],
                episode_title=hit["_source"]["episode_title"],
                published_at=date.fromisoformat(hit["_source"]["published_at"]),
                speakers=hit["_source"]["speakers"],
                text=hit["_source"]["text"],
                first_position=hit["_source"]["first_position"],
                last_position=hit["_source"]["last_position"],
                start=(
                    timedelta(seconds=hit["_source"]["start_seconds"])
                    if hit["_source"].get("start_seconds") is not None
                    else None
                ),
                score=float(hit["_score"]),
                strategy=STRATEGY,
            )
            for hit in hits
        ]
        span.set_attribute("retrieval.results", len(results))
        return results
