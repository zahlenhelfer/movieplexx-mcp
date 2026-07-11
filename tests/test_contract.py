"""Contract test: parse a checked-in golden API snapshot and assert the shape
our normalizer depends on. A failure here means the upstream JSON drifted.

Regenerate the snapshot when the drift is intentional:
    uv run python -c "import json; from movieplexx import scrape; \
        json.dump(scrape.fetch_raw(), open('tests/fixtures/filtered-films.golden.json','w'), \
        ensure_ascii=False, indent=2)"
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from movieplexx import scrape

GOLDEN = Path(__file__).parent / "fixtures" / "filtered-films.golden.json"

FILM_KEYS = {
    "slug", "film_title", "detail_id", "fsk", "length_min", "genre", "country",
    "distributor", "descriptors", "teaser", "poster_url", "trailer_url",
    "director", "scraped_at", "raw_json",
}
PERF_KEYS = {
    "performance_id", "film_slug", "film_title", "fsk", "length_min", "date",
    "time", "unixdatetime", "releases", "original_releases", "is_online",
    "is_sold_out", "is_not_bookable", "status", "booking_link",
    "auditorium_title", "site_id", "scraped_at", "raw_json",
}


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def normalized(raw):
    return scrape.normalize(raw, scraped_at="2026-07-11T00:00:00+00:00")


def test_top_level_shape(raw):
    assert isinstance(raw.get("films"), list) and raw["films"], "no films array"


def test_normalization_produces_rows(normalized):
    films, performances, stats = normalized
    assert films, "expected at least one film"
    assert performances, "expected at least one performance"
    assert stats["parse_errors"] == 0, "golden snapshot must normalize cleanly"


def test_film_rows_have_exact_keys(normalized):
    films, _, _ = normalized
    for film in films:
        assert set(film) == FILM_KEYS, f"film key drift: {set(film) ^ FILM_KEYS}"
        assert film["slug"], "film slug must be non-empty"
        assert film["film_title"], "film title must be non-empty"


def test_performance_rows_have_exact_keys(normalized):
    _, performances, _ = normalized
    for perf in performances:
        assert set(perf) == PERF_KEYS, f"perf key drift: {set(perf) ^ PERF_KEYS}"


def test_performance_field_types_and_invariants(normalized):
    _, performances, _ = normalized
    for perf in performances:
        assert isinstance(perf["performance_id"], int)
        assert isinstance(perf["unixdatetime"], int)
        assert perf["site_id"] is not None
        # date is ISO YYYY-MM-DD, time is HH:MM:SS
        assert len(perf["date"]) == 10 and perf["date"][4] == "-"
        assert len(perf["time"]) == 8 and perf["time"][2] == ":"
        assert perf["is_online"] in (0, 1)
        assert perf["is_sold_out"] in (0, 1)
        assert perf["is_not_bookable"] in (0, 1)
        # raw_json must round-trip
        assert json.loads(perf["raw_json"])["performanceID"] == perf["performance_id"]


def test_booking_links_point_to_cinuru(normalized):
    _, performances, _ = normalized
    linked = [p for p in performances if p["booking_link"]]
    assert linked, "expected at least one booking link"
    for perf in linked:
        assert "kinotickets.express/movieplex-buchholz/booking/" in perf["booking_link"]
