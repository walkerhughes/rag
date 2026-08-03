"""What is BM25's alone: the index as a projection, and the document it stores.

The behaviour shared with the other lexical strategy is in test_contract.py.
"""

from datetime import timedelta

import pytest
from opensearchpy import OpenSearch
from sqlalchemy.orm import Session

from retrieval import bm25
from retrieval.indexing import project_to_search

pytestmark = pytest.mark.integration


def test_the_index_rebuilds_from_postgres(indexed: OpenSearch, corpus: Session) -> None:
    """The index is a projection, so losing it entirely must cost nothing but time."""
    before = indexed.count(index=bm25.INDEX)["count"]
    indexed.indices.delete(index=bm25.INDEX)

    project_to_search(corpus, indexed, rebuild=True)

    assert indexed.count(index=bm25.INDEX)["count"] == before


def test_a_chunk_starting_at_zero_keeps_its_timestamp(indexed: OpenSearch) -> None:
    """A zero timedelta is falsy, so a truthiness test loses every first chunk's start."""
    found = bm25.search(indexed, "reinforcement learning", limit=20)
    starts = [item.start for item in found if item.first_position == 0]
    assert starts
    assert all(start is not None for start in starts)
    assert timedelta(0) in starts
