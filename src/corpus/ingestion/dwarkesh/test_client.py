"""Client tests. Responses are stubbed, so these never touch the network."""

import json
from datetime import date

import pytest

from corpus.ingestion.dwarkesh import client


def entry(slug: str, kind: str = "podcast") -> dict[str, str]:
    return {
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "canonical_url": f"https://www.dwarkesh.com/p/{slug}",
        "post_date": "2025-09-26T12:00:00.000Z",
        "type": kind,
    }


def test_listing_reads_the_publication_date_as_a_date() -> None:
    listing = client.EpisodeListing.model_validate(entry("richard-sutton"))
    assert listing.published_at == date(2025, 9, 26)
    assert listing.url == "https://www.dwarkesh.com/p/richard-sutton"
    assert listing.is_episode


def test_newsletters_and_restacks_are_not_episodes() -> None:
    assert not client.EpisodeListing.model_validate(entry("notes", "newsletter")).is_episode
    assert not client.EpisodeListing.model_validate(entry("shared", "restack")).is_episode


def test_listing_pages_until_it_has_enough_episodes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each archive page mixes newsletters in, so one page may not yield enough episodes."""
    pages = {
        0: [entry(f"news-{i}", "newsletter") for i in range(49)] + [entry("episode-a")],
        50: [entry("episode-b"), entry("episode-c")],
    }
    requested: list[int] = []

    def fake_get(url: str) -> str:
        offset = int(url.split("offset=")[1])
        requested.append(offset)
        return json.dumps(pages.get(offset, []))

    monkeypatch.setattr(client, "_get", fake_get)
    episodes = client.list_episodes(limit=2)

    assert [episode.slug for episode in episodes] == ["episode-a", "episode-b"]
    assert requested == [0, 50]


def test_listing_stops_when_the_archive_runs_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_get", lambda url: "[]")
    assert client.list_episodes(limit=10) == []


def test_a_non_json_archive_response_is_a_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_get", lambda url: "<html>error page</html>")
    with pytest.raises(client.FetchError, match="did not return JSON"):
        client.list_episodes()


def test_pagination_follows_the_delivered_count_not_the_requested_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The archive returns short pages, so paging by PAGE_SIZE skips the difference."""
    pages = {
        0: [entry("episode-a"), entry("episode-b")],
        2: [entry("episode-c")],
    }
    requested: list[int] = []

    def fake_get(url: str) -> str:
        offset = int(url.split("offset=")[1])
        requested.append(offset)
        return json.dumps(pages.get(offset, []))

    monkeypatch.setattr(client, "_get", fake_get)
    episodes = client.list_episodes(limit=3)

    assert [episode.slug for episode in episodes] == ["episode-a", "episode-b", "episode-c"]
    # The second request starts at 2, the number delivered, not at PAGE_SIZE.
    assert requested == [0, 2]
