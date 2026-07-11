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
| `METRICS_PORT` | `9000` | Prometheus endpoint port in loop mode (`<=0` disables) |
| `MCP_TRANSPORT` | `stdio` | `serve` transport: `stdio` (local) or `http` (remote) |
| `MCP_HOST` | `0.0.0.0` | HTTP bind address (`http` transport) |
| `MCP_PORT` | `8000` | HTTP port (`http` transport) |
| `MCP_PATH` | `/mcp` | HTTP endpoint path (`http` transport) |
| `MCP_ALLOWED_HOSTS` | — | Comma-separated `host:port` values to accept in the `Host` header, in addition to `localhost`/`127.0.0.1`/`::1` (`http` transport) |
| `MCP_AUTH_TOKEN` | — | Bearer token; **required** for `http` transport (fail-closed) |
| `MCP_TLS_CERTFILE` | — | Path to a TLS certificate; terminates HTTPS directly in the server. Must be set together with `MCP_TLS_KEYFILE` (`http` transport) |
| `MCP_TLS_KEYFILE` | — | Path to the matching TLS private key (`http` transport) |
| `LOG_LEVEL` | `INFO` | Logging level |

## MCP tools

- `list_showtimes(date?, film_slug?, only_upcoming?)` — performances, filterable
- `get_film(film_slug)` — full film record
- `list_films(only_current?)` — all known films
- `search_films(query)` — substring search over title/genre/director/distributor
- `film_history(film_slug)` — append-only scrape history (sold-out / status drift)

## Registering with an MCP client

The server speaks stdio. Add it to your client's server config (e.g. Claude
Desktop's `claude_desktop_config.json`). It only **reads** the DB, so populate it
first with at least one `scrape`.

Local (via `uv`):

```json
{
  "mcpServers": {
    "movieplexx": {
      "command": "uv",
      "args": ["run", "movieplexx", "serve"],
      "cwd": "/absolute/path/to/movieplexx-mcp",
      "env": { "DB_PATH": "/absolute/path/to/movieplexx-mcp/movieplexx.db" }
    }
  }
}
```

Docker (reads the shared `moviedata` volume the scraper writes):

```json
{
  "mcpServers": {
    "movieplexx": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "moviedata:/data:ro", "movieplexx-mcp", "serve"]
    }
  }
}
```

## Docker

```bash
docker compose up -d          # runs scraper (hourly loop) + shared volume
```

The MCP server is typically launched on demand by the client, e.g.:

```bash
docker run -i --rm -v moviedata:/data:ro movieplexx-mcp serve
```

## Remote serving on a NAS (HTTP transport)

By default `serve` speaks stdio and is spawned locally by the client. To run the
server long-lived on a NAS and reach it from your local Claude over the LAN, set
`MCP_TRANSPORT=http`. The endpoint is protected by a static bearer token and
**refuses to start without `MCP_AUTH_TOKEN`**.

Generate a token and start the networked `mcp` service (see `docker-compose.yml`,
which binds the port to the NAS LAN IP — adjust `192.168.1.50`):

```bash
echo "MCP_AUTH_TOKEN=$(openssl rand -hex 32)" >> .env   # .env is gitignored
echo "MCP_ALLOWED_HOSTS=192.168.1.50:8000" >> .env      # the LAN address clients connect to
docker compose up -d mcp
```

The server validates the incoming `Host` header (DNS-rebinding protection) and
otherwise only trusts `localhost`/`127.0.0.1`/`::1`. Without `MCP_ALLOWED_HOSTS`
set to the address in the URL above, remote requests fail with
`421 Invalid Host header` even though the bearer token is correct.

Register the remote server with your local Claude:

**Claude Code (CLI)** — native HTTP transport:

```bash
claude mcp add --transport http movieplexx http://192.168.1.50:8000/mcp \
  --header "Authorization: Bearer <TOKEN>"
```

**Claude Desktop** — no native remote-HTTP client, so use the `mcp-remote`
stdio↔HTTP bridge instead. Pass the full header
through `env` to avoid whitespace-splitting in `--header`:

```json
{
  "mcpServers": {
    "movieplexx": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://192.168.1.50:8000/mcp",
               "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer <TOKEN>" }
    }
  }
}
```

Quick smoke test (no token → 401):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.1.50:8000/mcp   # 401
```

Without TLS, the bearer token travels in cleartext on the wire — anyone who can
observe the LAN segment can read it. To terminate HTTPS directly in the server,
set `MCP_TLS_CERTFILE`/`MCP_TLS_KEYFILE` (both required together) and use
`https://` in the client config and smoke test above. A self-signed cert is
enough for LAN use:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout mcp-key.pem -out mcp-cert.pem -subj "/CN=192.168.1.50"
echo "MCP_TLS_CERTFILE=/data/mcp-cert.pem" >> .env
echo "MCP_TLS_KEYFILE=/data/mcp-key.pem" >> .env
```

This is intended for a trusted LAN. For off-LAN access put Tailscale/WireGuard in
front; for public exposure add a TLS reverse proxy. See `spec.md` §10.

## Container image (GHCR)

Multiarch images (`linux/amd64`, `linux/arm64`) are published to the GitHub
Container Registry by `.github/workflows/docker-publish.yml`:

```
ghcr.io/zahlenhelfer/movieplexx-mcp
```

| Tag | Published on | Meaning |
| --- | --- | --- |
| `dev` | every push to `main` | latest development build |
| `X.Y.Z`, `X.Y`, `X` | a published GitHub release `vX.Y.Z` | semver-pinned build |
| `latest` | a published GitHub release | newest release (never `dev`) |

Pull and run the published image instead of building locally:

```bash
docker pull ghcr.io/zahlenhelfer/movieplexx-mcp:latest

# scraper (hourly loop)
docker run -d --rm -v moviedata:/data ghcr.io/zahlenhelfer/movieplexx-mcp:latest scrape --loop

# MCP server (launched on demand by the client)
docker run -i --rm -v moviedata:/data:ro ghcr.io/zahlenhelfer/movieplexx-mcp:latest serve
```

The image is public — no `docker login` needed to pull. To cut a release image,
tag a commit and publish a GitHub release (`vX.Y.Z`); the workflow builds the
semver and `latest` tags.

## Metrics

In loop mode the scraper serves Prometheus metrics on `:${METRICS_PORT}/metrics`:

- `movieplexx_scrape_success_total` / `movieplexx_scrape_failure_total`
- `movieplexx_scrape_duration_seconds` (histogram)
- `movieplexx_films_seen` / `movieplexx_performances_seen` (last cycle)
- `movieplexx_parse_errors_total` — increments on a film that fails to normalize;
  alert on `> 0` to catch upstream schema drift.

## Tests

```bash
uv run pytest
```

`tests/test_contract.py` parses a checked-in golden snapshot
(`tests/fixtures/filtered-films.golden.json`) and asserts the exact field shape
the normalizer relies on. A failure means the upstream JSON drifted — regenerate
the snapshot (command in the test's docstring) once the change is understood.

## Etiquette

Honors robots.txt (`/programm/*` is allowed), uses a self-identifying User-Agent
with a contact address, and defaults to one request per hour.
