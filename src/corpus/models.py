"""Domain models for the canonical corpus.

Pure Pydantic, with no dependency on the persistence layer. Validation here is what stops
a malformed parse from reaching the database, so the rules are deliberately strict: a
parser that silently produces an episode with no turns is a bug, not an empty episode.
"""

from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _normalize(name: str) -> str:
    return " ".join(name.split())


class TranscriptSegment(BaseModel):
    """One speaker turn, at a known position in the episode."""

    position: int = Field(ge=0)
    speaker: str = Field(min_length=1)
    text: str = Field(min_length=1)
    # Absent in episodes whose transcript markup carries no inline timestamps.
    start: timedelta | None = None

    @field_validator("speaker", "text")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("speaker")
    @classmethod
    def normalize_speaker(cls, value: str) -> str:
        return _normalize(value)


class Episode(BaseModel):
    """A published episode and its ordered transcript."""

    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: date
    segments: list[TranscriptSegment] = Field(min_length=1)

    @field_validator("source_id", "title", "url")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def positions_are_contiguous_from_zero(self) -> "Episode":
        positions = [segment.position for segment in self.segments]
        if positions != list(range(len(positions))):
            raise ValueError("segment positions must be contiguous and start at zero")
        return self

    @property
    def speakers(self) -> list[str]:
        """Distinct speakers, in the order they first appear."""
        return list(dict.fromkeys(segment.speaker for segment in self.segments))
