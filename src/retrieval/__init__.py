"""The contract every retrieval strategy returns.

Lexical, vector and graph retrieval all answer with `Evidence`, so the agent can weigh
results from different strategies against each other and cite any of them the same way.
"""

import uuid
from datetime import date, timedelta

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """A retrieved passage, carrying everything needed to cite it."""

    chunk_id: uuid.UUID
    episode_source_id: str
    episode_title: str
    published_at: date
    speakers: list[str]
    text: str
    # Where the passage sits in the transcript, for resolving a citation back to source.
    first_position: int
    last_position: int
    start: timedelta | None
    score: float = Field(ge=0)
    # Which retrieval strategy produced this, so mixed results stay attributable.
    strategy: str
