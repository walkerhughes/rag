from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from corpus.models import Episode, TranscriptSegment


def turn(
    position: int, speaker: str = "Dwarkesh Patel", text: str = "A turn."
) -> TranscriptSegment:
    return TranscriptSegment(position=position, speaker=speaker, text=text)


def make_episode(segments: list[TranscriptSegment] | None = None) -> Episode:
    return Episode(
        source_id="richard-sutton",
        title="Richard Sutton",
        url="https://www.dwarkesh.com/p/richard-sutton",
        published_at=date(2025, 9, 26),
        segments=[turn(0), turn(1, "Richard Sutton")] if segments is None else segments,
    )


def test_episode_with_no_segments_is_rejected() -> None:
    """A parser that matches nothing yields an empty transcript rather than an error."""
    with pytest.raises(ValidationError):
        make_episode(segments=[])


def test_positions_must_be_contiguous_from_zero() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        make_episode(segments=[turn(0), turn(2)])

    with pytest.raises(ValidationError, match="contiguous"):
        make_episode(segments=[turn(1), turn(2)])


def test_blank_text_and_speakers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TranscriptSegment(position=0, speaker="Sutton", text="   ")
    with pytest.raises(ValidationError):
        TranscriptSegment(position=0, speaker="", text="A turn.")


def test_speaker_whitespace_is_normalized() -> None:
    """Turn headers carry stray whitespace, so the same person must not become two."""
    parsed = TranscriptSegment(position=0, speaker="  Richard   Sutton ", text="A turn.")
    assert parsed.speaker == "Richard Sutton"


def test_start_time_is_optional() -> None:
    """Some episodes' transcript markup carries no inline timestamps."""
    assert TranscriptSegment(position=0, speaker="A", text="B").start is None
    timed = TranscriptSegment(position=0, speaker="A", text="B", start=timedelta(minutes=31))
    assert timed.start == timedelta(minutes=31)


def test_speakers_are_distinct_and_in_first_appearance_order() -> None:
    parsed = make_episode(
        segments=[
            turn(0, "Dwarkesh Patel"),
            turn(1, "Richard Sutton"),
            turn(2, "Dwarkesh Patel"),
        ]
    )
    assert parsed.speakers == ["Dwarkesh Patel", "Richard Sutton"]
