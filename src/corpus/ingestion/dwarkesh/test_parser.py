"""Parser tests. Committed fixtures only, so these never touch the network."""

from datetime import timedelta
from pathlib import Path

import pytest

from corpus.ingestion.dwarkesh.parser import ParseError, article_body, parse_transcript

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text()


def test_sutton_transcript_is_parsed_in_order() -> None:
    segments = parse_transcript(fixture("richard-sutton"))

    assert [segment.position for segment in segments] == list(range(len(segments)))
    assert {segment.speaker for segment in segments} == {"Dwarkesh Patel", "Richard Sutton"}
    assert all(segment.text for segment in segments)


def test_the_transcript_repeated_below_the_comments_is_not_read_twice() -> None:
    """Live pages embed the whole transcript a second time, after the discussion section.

    The committed fixtures have their script tags removed, which happens to drop that
    second copy, so the boundary is checked against the structure directly.
    """
    turns = "<p><strong>Dwarkesh Patel</strong></p><p>A question.</p>"
    html = (
        f'<div class="available-content">{turns}</div>'
        f'<div id="discussion">comments</div>'
        f'<script>window._preloads = {{"body": "{turns}"}}</script>'
    )
    segments = parse_transcript(html)

    assert len(segments) == 1, "the copy below the comments was read as extra turns"
    assert "_preloads" not in article_body(html)


def test_no_long_turn_is_read_twice_from_a_real_page() -> None:
    segments = parse_transcript(fixture("richard-sutton"))
    texts = [segment.text for segment in segments if len(segment.text) > 200]
    assert len(texts) == len(set(texts)), "a long turn appears twice"
    assert len(segments) > 100


def test_speaker_names_wrapped_in_spans_are_recognised() -> None:
    """One markup variant nests the name inside a further span."""
    segments = parse_transcript(fixture("grant-sanderson-2"))

    assert {segment.speaker for segment in segments} == {"Dwarkesh Patel", "Grant Sanderson"}
    assert len(segments) > 50


def test_timestamps_are_read_when_present_and_absent_otherwise() -> None:
    timed = parse_transcript(fixture("richard-sutton"))
    assert all(segment.start is not None for segment in timed)
    assert timed[0].start == timedelta(0)

    untimed = parse_transcript(fixture("grant-sanderson-2"))
    assert all(segment.start is None for segment in untimed)


def test_chapter_links_are_not_mistaken_for_turns() -> None:
    """Chapter markers look like '(00:13:04) - Do humans do imitation learning?'."""
    segments = parse_transcript(fixture("richard-sutton"))
    assert not any(segment.speaker.startswith("(") for segment in segments)
    assert not any(segment.text.startswith("(00:") for segment in segments)


def test_a_page_without_an_article_is_rejected() -> None:
    with pytest.raises(ParseError, match="article body"):
        parse_transcript("<html><body>nothing here</body></html>")


def test_a_page_without_turns_is_rejected() -> None:
    """Silently returning an empty transcript is the failure mode worth preventing."""
    html = '<div class="available-content"><p>Just prose, no speakers.</p></div>'
    with pytest.raises(ParseError, match="speaker turns"):
        parse_transcript(html)


def test_a_bold_run_inside_a_sentence_is_not_a_turn_header() -> None:
    html = (
        '<div class="available-content">'
        "<p><strong>Dwarkesh Patel</strong></p>"
        "<p>He said <strong>this bit</strong> was the important part.</p>"
        "</div>"
    )
    segments = parse_transcript(html)
    assert len(segments) == 1
    assert segments[0].text == "He said this bit was the important part."
