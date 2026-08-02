"""Turning a Dwarkesh post page into a canonical episode.

Pure functions over HTML, so parser tests need no network.
"""

import re
from datetime import timedelta

from corpus.models import TranscriptSegment

TAGS = re.compile(r"<[^>]+>")
PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)
TIMESTAMP = re.compile(r"^\(?(\d{1,2}):(\d{2}):(\d{2})\)?$")
BREAK = re.compile(r"<br\s*/?>", re.I)

# A turn header is a bolded speaker name, optionally followed by a timestamp. Matching on
# structure rather than on exact markup covers the four variants the site uses: a bare
# name, a name with an inline timestamp, a name wrapped in a further span, and a name
# followed by a line break and the turn's own words in the same paragraph.
HEADER = re.compile(r"^\s*<strong>(?P<name>.*?)</strong>(?P<rest>.*)$", re.S)
LONGEST_SPEAKER_NAME = 60

ARTICLE_OPEN = "available-content"
# Pages render the whole transcript a second time below the comments, so parsing has to
# stop here or every turn is read twice.
ARTICLE_CLOSE = '<div id="discussion"'


class ParseError(Exception):
    """The page holds no transcript this parser recognises."""


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub("", fragment)).strip()


def article_body(html: str) -> str:
    start = html.find(ARTICLE_OPEN)
    if start == -1:
        raise ParseError("page has no article body")
    body = html[start:]
    end = body.find(ARTICLE_CLOSE)
    return body[:end] if end != -1 else body


def _turn_start(paragraph: str) -> tuple[str, timedelta | None, str] | None:
    """The speaker, the timestamp, and any turn text sharing the header's paragraph.

    Some episodes put the whole turn in one paragraph, with the name and timestamp
    separated from the words by a line break.
    """
    head, *remainder = BREAK.split(paragraph.strip(), maxsplit=1)
    match = HEADER.match(head.strip())
    if match is None:
        return None
    name = _plain(match.group("name"))
    if not name or len(name) > LONGEST_SPEAKER_NAME:
        return None

    start = None
    trailing = _plain(match.group("rest"))
    if trailing:
        stamp = TIMESTAMP.match(trailing)
        if stamp is None:
            return None
        hours, minutes, seconds = (int(part) for part in stamp.groups())
        start = timedelta(hours=hours, minutes=minutes, seconds=seconds)

    return name, start, _plain(remainder[0]) if remainder else ""


def parse_transcript(html: str) -> list[TranscriptSegment]:
    """Ordered speaker turns. Text before the first header is front matter and is dropped."""
    segments: list[TranscriptSegment] = []
    speaker: str | None = None
    start: timedelta | None = None
    paragraphs: list[str] = []

    def close_turn() -> None:
        nonlocal paragraphs
        if speaker is not None:
            text = " ".join(paragraphs).strip()
            if text:
                segments.append(
                    TranscriptSegment(
                        position=len(segments), speaker=speaker, text=text, start=start
                    )
                )
        paragraphs = []

    for match in PARAGRAPH.finditer(article_body(html)):
        header = _turn_start(match.group(1))
        if header is not None:
            close_turn()
            speaker, start, leading = header
            if leading:
                paragraphs.append(leading)
        elif speaker is not None:
            body = _plain(match.group(1))
            if body:
                paragraphs.append(body)
    close_turn()

    if not segments:
        raise ParseError("page has no speaker turns")
    return segments
