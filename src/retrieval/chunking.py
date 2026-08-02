"""Grouping transcript turns into retrieval units.

A turn is the wrong unit on its own: a quarter of them are under twenty words and a
tenth run past three hundred. Chunks therefore pack consecutive turns up to a target
size, and split a turn that exceeds the ceiling on its own at sentence boundaries.

Chunks never span episodes, and each one records the range of turns it covers, so any
passage can be resolved back to its speaker and position in the transcript.
"""

import re
from datetime import timedelta

from pydantic import BaseModel, Field

from corpus.models import TranscriptSegment

CHUNKER_VERSION = "1"
TARGET_WORDS = 200
LONGEST_CHUNK_WORDS = 400

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class Chunk(BaseModel):
    """One retrieval unit, covering turns `first_position` to `last_position`."""

    ordinal: int = Field(ge=0)
    first_position: int = Field(ge=0)
    last_position: int = Field(ge=0)
    speakers: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)
    # The timestamp of the first turn, absent when the episode carries none.
    start: timedelta | None = None


def _words(text: str) -> int:
    return len(text.split())


def _sentences(text: str) -> list[str]:
    return [piece for piece in SENTENCE_END.split(text) if piece.strip()]


def _split_long_turn(text: str) -> list[str]:
    """Sentence-aligned pieces, each within the target where the sentences allow it."""
    pieces: list[str] = []
    current: list[str] = []
    for sentence in _sentences(text):
        if current and _words(" ".join(current)) + _words(sentence) > TARGET_WORDS:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces or [text]


def chunk_segments(segments: list[TranscriptSegment]) -> list[Chunk]:
    """Deterministic: the same turns always produce the same chunks."""
    chunks: list[Chunk] = []
    pending: list[TranscriptSegment] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                first_position=pending[0].position,
                last_position=pending[-1].position,
                speakers=list(dict.fromkeys(segment.speaker for segment in pending)),
                text=" ".join(segment.text for segment in pending),
                start=pending[0].start,
            )
        )
        pending = []

    for segment in sorted(segments, key=lambda item: item.position):
        if _words(segment.text) > LONGEST_CHUNK_WORDS:
            flush()
            for piece in _split_long_turn(segment.text):
                chunks.append(
                    Chunk(
                        ordinal=len(chunks),
                        first_position=segment.position,
                        last_position=segment.position,
                        speakers=[segment.speaker],
                        text=piece,
                        start=segment.start,
                    )
                )
            continue

        if (
            pending
            and _words(" ".join(s.text for s in pending)) + _words(segment.text) > TARGET_WORDS
        ):
            flush()
        pending.append(segment)

    flush()
    return chunks
