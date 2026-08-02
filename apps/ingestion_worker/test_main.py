"""Worker tests. Fetching is stubbed and nothing here needs a database."""

from datetime import date
from pathlib import Path

import pytest
from apps.ingestion_worker.main import describe, dry_run

from corpus.ingestion.dwarkesh import client

FIXTURES = Path(__file__).parents[2] / "src/corpus/ingestion/dwarkesh/fixtures"


def listing(slug: str = "richard-sutton") -> client.EpisodeListing:
    return client.EpisodeListing(
        slug=slug,
        title="Richard Sutton",
        canonical_url=f"https://www.dwarkesh.com/p/{slug}",
        post_date=date(2025, 9, 26),
        type="podcast",
    )


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch_page(slug: str) -> str:
        path = FIXTURES / f"{slug}.html"
        if not path.exists():
            raise client.FetchError(f"{slug}: not found")
        return path.read_text()

    monkeypatch.setattr(client, "fetch_page", fetch_page)


def test_a_dry_run_reports_the_parse_and_succeeds(
    offline: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert dry_run([listing()]) == 0

    report = capsys.readouterr().out
    assert "richard-sutton" in report
    assert "Dwarkesh Patel, Richard Sutton" in report
    assert "turns" in report


def test_a_dry_run_fails_when_an_episode_cannot_be_parsed(
    offline: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bad parse has to be visible in the exit code, not just in the output."""
    assert dry_run([listing("missing-episode")]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_a_dry_run_keeps_going_after_one_failure(
    offline: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert dry_run([listing("missing-episode"), listing()]) == 1

    captured = capsys.readouterr()
    assert "FAILED" in captured.err
    assert "richard-sutton" in captured.out


def test_the_report_shows_what_distinguishes_a_good_parse_from_a_bad_one(
    offline: None,
) -> None:
    from corpus.ingestion.dwarkesh.pipeline import fetch_and_parse

    report = describe(fetch_and_parse(listing()))

    for field in ("title", "turns", "speakers", "words", "timestamps", "first", "last"):
        assert field in report
