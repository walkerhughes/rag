from datetime import timedelta
from itertools import pairwise

from corpus.models import TranscriptSegment
from retrieval.chunking import LONGEST_CHUNK_WORDS, TARGET_WORDS, chunk_segments


def turn(position: int, words: int, speaker: str = "Dwarkesh Patel") -> TranscriptSegment:
    return TranscriptSegment(position=position, speaker=speaker, text=" ".join(["word"] * words))


def test_short_turns_are_packed_together() -> None:
    """A quarter of real turns are under twenty words, which retrieve badly alone."""
    chunks = chunk_segments([turn(i, 10) for i in range(20)])

    assert len(chunks) < 20
    assert all(len(chunk.text.split()) <= TARGET_WORDS for chunk in chunks)


def test_a_turn_longer_than_the_ceiling_is_split() -> None:
    sentences = " ".join(["word " * 30 + "." for _ in range(30)])
    segment = TranscriptSegment(position=0, speaker="Richard Sutton", text=sentences)

    chunks = chunk_segments([segment])

    assert len(chunks) > 1
    assert all(chunk.first_position == 0 and chunk.last_position == 0 for chunk in chunks)
    assert all(chunk.speakers == ["Richard Sutton"] for chunk in chunks)


def test_every_chunk_records_the_turns_it_covers() -> None:
    chunks = chunk_segments([turn(i, 60) for i in range(10)])

    assert chunks[0].first_position == 0
    assert chunks[-1].last_position == 9
    for chunk in chunks:
        assert chunk.first_position <= chunk.last_position
    # Contiguous and gapless, so no turn is dropped or counted twice.
    for earlier, later in pairwise(chunks):
        assert later.first_position == earlier.last_position + 1


def test_chunks_are_numbered_from_zero_in_order() -> None:
    chunks = chunk_segments([turn(i, 80) for i in range(12)])
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_speakers_are_recorded_in_order_without_repeats() -> None:
    segments = [
        turn(0, 50, "Dwarkesh Patel"),
        turn(1, 50, "Richard Sutton"),
        turn(2, 50, "Dwarkesh Patel"),
    ]
    chunk = chunk_segments(segments)[0]
    assert chunk.speakers == ["Dwarkesh Patel", "Richard Sutton"]


def test_the_first_turns_timestamp_carries_onto_the_chunk() -> None:
    segments = [
        TranscriptSegment(position=0, speaker="A", text="Hello.", start=timedelta(minutes=5)),
        TranscriptSegment(position=1, speaker="A", text="More.", start=timedelta(minutes=6)),
    ]
    assert chunk_segments(segments)[0].start == timedelta(minutes=5)


def test_chunking_is_deterministic() -> None:
    """Re-chunking unchanged turns has to produce identical chunks, or embeddings churn."""
    segments = [turn(i, 40 + (i % 7) * 15) for i in range(30)]
    assert chunk_segments(segments) == chunk_segments(segments)


def test_out_of_order_turns_are_sorted_before_chunking() -> None:
    segments = [turn(2, 30), turn(0, 30), turn(1, 30)]
    chunk = chunk_segments(segments)[0]
    assert chunk.first_position == 0
    assert chunk.last_position == 2


def test_no_chunk_greatly_exceeds_the_ceiling() -> None:
    segments = [turn(i, 190) for i in range(6)]
    for chunk in chunk_segments(segments):
        assert len(chunk.text.split()) <= LONGEST_CHUNK_WORDS
