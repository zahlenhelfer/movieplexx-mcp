"""Fetch and normalize the Movieplexx filtered-films JSON endpoint.

The endpoint returns every current film with all of its performances in one
response. We flatten it into two lists of plain dicts (films + performances)
and keep the raw source object on each row for schema-drift resilience.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("movieplexx.scrape")

DEFAULT_URL = "https://movieplexx.de/programm/api/filtered-films"
DEFAULT_UA = "MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_raw(url: str | None = None, user_agent: str | None = None,
              timeout: float = 20.0) -> dict[str, Any]:
    """Perform the single HTTP GET and return the parsed JSON body."""
    url = url or os.environ.get("TARGET_URL", DEFAULT_URL)
    user_agent = user_agent or os.environ.get("USER_AGENT", DEFAULT_UA)
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    with httpx.Client(http2=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _to_int(value: Any) -> int | None:
    """Coerce API values (which may be str, int or None) to int."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_film(film: dict[str, Any], scraped_at: str) -> dict[str, Any]:
    """Flatten one film object into a `films` row."""
    cast = film.get("castAndCrew")
    return {
        "slug": film.get("slug"),
        "film_title": film.get("filmTitle"),
        "detail_id": _to_int(film.get("detailId")),
        "fsk": film.get("fsk"),
        "length_min": _to_int(film.get("length")),
        "genre": film.get("genre"),
        "country": film.get("country"),
        "distributor": film.get("distributor"),
        "descriptors": film.get("descriptor"),
        "teaser": film.get("teaser"),
        "poster_url": film.get("poster"),
        "trailer_url": film.get("trailer"),
        "director": cast.get("Regie") if isinstance(cast, dict) else None,
        "scraped_at": scraped_at,
        "raw_json": json.dumps(film, ensure_ascii=False),
    }


def normalize_performances(film: dict[str, Any], scraped_at: str) -> list[dict[str, Any]]:
    """Flatten every performance nested under one film into `performances` rows.

    Structure: film["performances"] is a list of site-groups, each of which has
    its own nested "performances" dict keyed by performance id.
    """
    rows: list[dict[str, Any]] = []
    for group in film.get("performances") or []:
        site_id = _to_int(group.get("siteId"))
        for _pid, perf in (group.get("performances") or {}).items():
            releases = perf.get("releasesCombined")
            rows.append({
                "performance_id": _to_int(perf.get("performanceID")),
                "film_slug": film.get("slug"),
                "film_title": film.get("filmTitle"),
                "fsk": film.get("fsk"),
                "length_min": _to_int(film.get("length")),
                "date": perf.get("date"),
                "time": perf.get("time"),
                "unixdatetime": _to_int(perf.get("unixdatetime")),
                "releases": ",".join(releases) if isinstance(releases, list) else None,
                "original_releases": perf.get("originalReleases") or None,
                "is_online": int(bool(perf.get("isOnline"))),
                "is_sold_out": int(bool(perf.get("isSoldOut"))),
                "is_not_bookable": int(bool(perf.get("isNotBookable"))),
                "status": perf.get("status"),
                "booking_link": perf.get("bookingLink"),
                "auditorium_title": perf.get("performanceAuditoriumAttributeTitle"),
                "site_id": site_id if site_id is not None else _to_int(perf.get("siteId")),
                "scraped_at": scraped_at,
                "raw_json": json.dumps(perf, ensure_ascii=False),
            })
    return rows


def normalize(data: dict[str, Any], scraped_at: str | None = None
              ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Return (films, performances, stats) normalized from a raw API response.

    stats carries {"parse_errors", "films_skipped"} so callers can surface
    schema drift (a film that fails to normalize) as a metric/alert without the
    whole scrape crashing.
    """
    scraped_at = scraped_at or _now_iso()
    films: list[dict[str, Any]] = []
    performances: list[dict[str, Any]] = []
    parse_errors = 0
    films_skipped = 0
    for film in data.get("films") or []:
        if not film.get("slug"):
            films_skipped += 1
            continue
        try:
            films.append(normalize_film(film, scraped_at))
            performances.extend(normalize_performances(film, scraped_at))
        except Exception:  # noqa: BLE001 - one bad film must not lose the rest
            parse_errors += 1
            log.exception("failed to normalize film slug=%s", film.get("slug"))
    stats = {"parse_errors": parse_errors, "films_skipped": films_skipped}
    return films, performances, stats


def scrape(url: str | None = None, user_agent: str | None = None
           ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Fetch live and normalize in one call."""
    scraped_at = _now_iso()
    data = fetch_raw(url, user_agent)
    return normalize(data, scraped_at)
