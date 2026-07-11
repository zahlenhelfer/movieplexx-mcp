"""SQLite persistence: current-state upsert plus append-only history log."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_PATH = "/data/movieplexx.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS performances (
  performance_id     INTEGER PRIMARY KEY,
  film_slug          TEXT NOT NULL,
  film_title         TEXT NOT NULL,
  fsk                TEXT,
  length_min         INTEGER,
  date               TEXT NOT NULL,
  time               TEXT NOT NULL,
  unixdatetime       INTEGER NOT NULL,
  releases           TEXT,
  original_releases  TEXT,
  is_online          INTEGER NOT NULL,
  is_sold_out        INTEGER NOT NULL,
  is_not_bookable    INTEGER NOT NULL,
  status             TEXT,
  booking_link       TEXT,
  auditorium_title   TEXT,
  site_id            INTEGER NOT NULL,
  first_seen         TEXT NOT NULL,
  last_seen          TEXT NOT NULL,
  raw_json           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_perf_date ON performances(date);
CREATE INDEX IF NOT EXISTS idx_perf_slug ON performances(film_slug);
CREATE INDEX IF NOT EXISTS idx_perf_unix ON performances(unixdatetime);

CREATE TABLE IF NOT EXISTS performance_history (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  performance_id     INTEGER NOT NULL,
  film_slug          TEXT,
  scraped_at         TEXT NOT NULL,
  is_sold_out        INTEGER,
  is_online          INTEGER,
  status             TEXT,
  releases           TEXT,
  film_title         TEXT,
  raw_json           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hist_perf ON performance_history(performance_id);
CREATE INDEX IF NOT EXISTS idx_hist_time ON performance_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_hist_slug ON performance_history(film_slug);

CREATE TABLE IF NOT EXISTS films (
  slug            TEXT PRIMARY KEY,
  film_title      TEXT NOT NULL,
  detail_id       INTEGER,
  fsk             TEXT,
  length_min      INTEGER,
  genre           TEXT,
  country         TEXT,
  distributor     TEXT,
  descriptors     TEXT,
  teaser          TEXT,
  poster_url      TEXT,
  trailer_url     TEXT,
  director        TEXT,
  first_seen      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  raw_json        TEXT NOT NULL
);
"""


def db_path() -> str:
    return os.environ.get("DB_PATH", DEFAULT_DB_PATH)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: str | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """Open a connection. Read-only mode is used by the MCP server."""
    path = path or db_path()
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _upsert_film(conn: sqlite3.Connection, film: dict[str, Any], now: str) -> None:
    conn.execute(
        """
        INSERT INTO films (
            slug, film_title, detail_id, fsk, length_min, genre, country,
            distributor, descriptors, teaser, poster_url, trailer_url, director,
            first_seen, last_seen, raw_json
        ) VALUES (
            :slug, :film_title, :detail_id, :fsk, :length_min, :genre, :country,
            :distributor, :descriptors, :teaser, :poster_url, :trailer_url, :director,
            :first_seen, :last_seen, :raw_json
        )
        ON CONFLICT(slug) DO UPDATE SET
            film_title  = excluded.film_title,
            detail_id   = excluded.detail_id,
            fsk         = excluded.fsk,
            length_min  = excluded.length_min,
            genre       = excluded.genre,
            country     = excluded.country,
            distributor = excluded.distributor,
            descriptors = excluded.descriptors,
            teaser      = excluded.teaser,
            poster_url  = excluded.poster_url,
            trailer_url = excluded.trailer_url,
            director    = excluded.director,
            last_seen   = excluded.last_seen,
            raw_json    = excluded.raw_json
        """,
        {**film, "first_seen": now, "last_seen": now},
    )


def _upsert_performance(conn: sqlite3.Connection, perf: dict[str, Any], now: str) -> None:
    conn.execute(
        """
        INSERT INTO performances (
            performance_id, film_slug, film_title, fsk, length_min, date, time,
            unixdatetime, releases, original_releases, is_online, is_sold_out,
            is_not_bookable, status, booking_link, auditorium_title, site_id,
            first_seen, last_seen, raw_json
        ) VALUES (
            :performance_id, :film_slug, :film_title, :fsk, :length_min, :date, :time,
            :unixdatetime, :releases, :original_releases, :is_online, :is_sold_out,
            :is_not_bookable, :status, :booking_link, :auditorium_title, :site_id,
            :first_seen, :last_seen, :raw_json
        )
        ON CONFLICT(performance_id) DO UPDATE SET
            film_slug         = excluded.film_slug,
            film_title        = excluded.film_title,
            fsk               = excluded.fsk,
            length_min        = excluded.length_min,
            date              = excluded.date,
            time              = excluded.time,
            unixdatetime      = excluded.unixdatetime,
            releases          = excluded.releases,
            original_releases = excluded.original_releases,
            is_online         = excluded.is_online,
            is_sold_out       = excluded.is_sold_out,
            is_not_bookable   = excluded.is_not_bookable,
            status            = excluded.status,
            booking_link      = excluded.booking_link,
            auditorium_title  = excluded.auditorium_title,
            site_id           = excluded.site_id,
            last_seen         = excluded.last_seen,
            raw_json          = excluded.raw_json
        """,
        {**perf, "first_seen": now, "last_seen": now},
    )


def _append_history(conn: sqlite3.Connection, perf: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO performance_history (
            performance_id, film_slug, scraped_at, is_sold_out, is_online,
            status, releases, film_title, raw_json
        ) VALUES (
            :performance_id, :film_slug, :scraped_at, :is_sold_out, :is_online,
            :status, :releases, :film_title, :raw_json
        )
        """,
        perf,
    )


def save(conn: sqlite3.Connection, films: list[dict[str, Any]],
         performances: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert films + performances and append one history row per performance."""
    now = _now_iso()
    for film in films:
        _upsert_film(conn, film, now)
    for perf in performances:
        if perf.get("performance_id") is None:
            continue
        _upsert_performance(conn, perf, now)
        _append_history(conn, perf)
    conn.commit()
    return {"films": len(films), "performances": len(performances)}
