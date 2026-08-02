"""Fetching episode listings and post pages from dwarkesh.com."""

import json
import urllib.error
import urllib.request
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

ARCHIVE_URL = "https://www.dwarkesh.com/api/v1/archive"
POST_URL = "https://www.dwarkesh.com/p/{slug}"
USER_AGENT = "rag-ingestion/0.1 (+https://github.com/walkerhughes/rag)"
TIMEOUT_SECONDS = 30
PODCAST = "podcast"
# The archive endpoint rejects larger pages, and truncates responses well below its own
# limit, so pagination follows the delivered count rather than this one.
PAGE_SIZE = 50
MAX_PAGES = 20


class FetchError(Exception):
    """The source could not be reached, or answered with something unusable."""


class EpisodeListing(BaseModel):
    """One archive entry. Newsletter and restack posts carry no transcript."""

    model_config = ConfigDict(populate_by_name=True)

    slug: str
    title: str
    url: str = Field(alias="canonical_url")
    published_at: date = Field(alias="post_date")
    kind: str = Field(alias="type")

    @field_validator("published_at", mode="before")
    @classmethod
    def date_only(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return value

    @property
    def is_episode(self) -> bool:
        return self.kind == PODCAST


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body: bytes = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise FetchError(f"{url}: {error}") from error
    return body.decode("utf-8", errors="replace")


def _archive_page(offset: int) -> list[EpisodeListing]:
    raw = _get(f"{ARCHIVE_URL}?sort=new&limit={PAGE_SIZE}&offset={offset}")
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FetchError(f"archive did not return JSON: {error}") from error
    return [EpisodeListing.model_validate(entry) for entry in entries]


def list_episodes(limit: int = 20) -> list[EpisodeListing]:
    """Podcast episodes, newest first. Pages the archive until enough are found.

    The archive mixes newsletters and restacks in with episodes, so a page yields fewer
    episodes than entries.
    """
    episodes: list[EpisodeListing] = []
    offset = 0
    for _ in range(MAX_PAGES):
        entries = _archive_page(offset)
        if not entries:
            break
        # The archive often returns fewer entries than asked for. Advancing by the
        # requested size instead of the delivered size silently skips the difference.
        offset += len(entries)
        episodes.extend(entry for entry in entries if entry.is_episode)
        if len(episodes) >= limit:
            break
    return episodes[:limit]


def fetch_page(slug: str) -> str:
    return _get(POST_URL.format(slug=slug))
