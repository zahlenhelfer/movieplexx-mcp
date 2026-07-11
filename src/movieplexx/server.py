"""MCP server exposing the mirrored program read-only over stdio."""

from __future__ import annotations

import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import store

mcp = FastMCP("movieplexx-buchholz")


def _query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    conn = store.connect(read_only=True)
    try:
        rows = conn.execute(sql, params or []).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@mcp.tool()
def list_showtimes(date: str | None = None, film_slug: str | None = None,
                   only_upcoming: bool = False) -> list[dict]:
    """List performances, optionally filtered by ISO date (YYYY-MM-DD) or film slug.

    Set only_upcoming to hide performances whose date lies in the past.
    """
    sql = (
        "SELECT performance_id, film_title, film_slug, date, time, releases, "
        "fsk, is_sold_out, is_online, booking_link, auditorium_title "
        "FROM performances WHERE 1=1"
    )
    params: list[Any] = []
    if date:
        sql += " AND date = ?"
        params.append(date)
    if film_slug:
        sql += " AND film_slug = ?"
        params.append(film_slug)
    if only_upcoming:
        sql += " AND date >= date('now')"
    sql += " ORDER BY unixdatetime"
    return _query(sql, params)


@mcp.tool()
def get_film(film_slug: str) -> dict | None:
    """Return the full film record for one slug, or null if unknown."""
    rows = _query(
        "SELECT slug, film_title, fsk, length_min, genre, country, distributor, "
        "descriptors, teaser, poster_url, trailer_url, director, first_seen, last_seen "
        "FROM films WHERE slug = ?",
        [film_slug],
    )
    return rows[0] if rows else None


@mcp.tool()
def search_films(query: str) -> list[dict]:
    """Search films by title, genre, director or distributor (case-insensitive substring)."""
    like = f"%{query}%"
    return _query(
        "SELECT slug, film_title, fsk, length_min, genre, director "
        "FROM films "
        "WHERE film_title LIKE ? OR genre LIKE ? OR director LIKE ? OR distributor LIKE ? "
        "ORDER BY film_title",
        [like, like, like, like],
    )


@mcp.tool()
def film_history(film_slug: str) -> list[dict]:
    """Return the append-only scrape history for a film's performances (sold-out / status drift)."""
    return _query(
        "SELECT scraped_at, performance_id, is_sold_out, is_online, status, releases "
        "FROM performance_history WHERE film_slug = ? "
        "ORDER BY scraped_at, performance_id",
        [film_slug],
    )


@mcp.tool()
def list_films(only_current: bool = True) -> list[dict]:
    """List all known films. With only_current, restrict to films with an upcoming performance."""
    if only_current:
        return _query(
            "SELECT DISTINCT f.slug, f.film_title, f.fsk, f.genre "
            "FROM films f JOIN performances p ON p.film_slug = f.slug "
            "WHERE p.date >= date('now') ORDER BY f.film_title"
        )
    return _query("SELECT slug, film_title, fsk, genre FROM films ORDER BY film_title")


if __name__ == "__main__":
    mcp.run()
