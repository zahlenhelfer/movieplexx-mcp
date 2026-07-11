# movieplexx-mcp

MCP server that mirrors and historically archives the current cinema program of
**Movieplexx Buchholz**.

It polls the cinema's internal JSON endpoint
(`https://movieplexx.de/programm/api/filtered-films`) — which returns every
current film with all showtimes, booking links, formats and metadata in a single
response — normalizes it into SQLite, keeps an append-only history log, and
exposes the data read-only to an MCP client.

## Architecture

One image, two roles selected by command:

```
scraper (CLI)  ── hourly ──▶  SQLite (volume)  ── read-only ──▶  mcp-server (stdio) ──▶ Claude
```

- `scrape` — fetch, upsert current performances, append a history snapshot
- `serve` — run the MCP server (stdio), reading the same DB read-only

## Layout

- `src/movieplexx/scrape.py` — HTTP fetch + normalization of the API response
- `src/movieplexx/store.py` — SQLite schema, upsert, append-only history
- `src/movieplexx/cli.py` — `scrape [--loop]`, `serve`
- `src/movieplexx/server.py` — FastMCP tools

## Local usage

```bash
uv sync
DB_PATH=./movieplexx.db uv run movieplexx scrape      # one fetch + store
DB_PATH=./movieplexx.db uv run movieplexx serve       # MCP server over stdio
```

## Configuration (environment)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_PATH` | `/data/movieplexx.db` | SQLite file location |
| `TARGET_URL` | `.../programm/api/filtered-films` | Source endpoint |
| `USER_AGENT` | `MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)` | Self-identifying UA |
| `POLL_INTERVAL_SECONDS` | `3600` | Loop interval for `scrape --loop` |
| `LOG_LEVEL` | `INFO` | Logging level |

## MCP tools

- `list_showtimes(date?, film_slug?, only_upcoming?)` — performances, filterable
- `get_film(film_slug)` — full film record
- `list_films(only_current?)` — all known films
- `search_films(query)` — substring search over title/genre/director/distributor
- `film_history(film_slug)` — append-only scrape history (sold-out / status drift)

## Docker

```bash
docker compose up -d          # runs scraper (hourly loop) + shared volume
```

The MCP server is typically launched on demand by the client, e.g.:

```bash
docker run -i --rm -v moviedata:/data:ro movieplexx-mcp serve
```

## Etiquette

Honors robots.txt (`/programm/*` is allowed), uses a self-identifying User-Agent
with a contact address, and defaults to one request per hour.
