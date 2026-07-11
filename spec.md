# movieplexx-mcp — Architektur & Ist-Zustand

Stand: 2026-07-11 · MCP-Server, der das Kinoprogramm des Movieplexx Buchholz
spiegelt, historisch archiviert und lokal sowie remote per MCP bereitstellt.

## 1. Überblick

Ein Scraper pollt stündlich den internen JSON-Endpoint von movieplexx.de,
normalisiert die Antwort und schreibt sie in SQLite (aktueller Stand +
Append-Log). Ein MCP-Server liest dieselbe DB read-only und stellt sie einem
Claude-Client als Tools zur Verfügung — entweder lokal per stdio oder
dauerhaft über HTTP (z.B. von einem NAS aus, LAN-only, mit Bearer-Auth).

Ein Docker-Image, zwei Rollen per Startkommando (`scrape` / `serve`).

## 2. Architektur

```
┌────────────────┐  stündlich   ┌──────────────┐
│  scraper (CLI)  │─────────────▶│  SQLite-DB   │
│  Python-Loop    │              │  (Volume)    │
└────────────────┘              └──────┬───────┘
                                        │ read-only
                                        ▼
                                 ┌──────────────┐
                                 │  mcp-server  │  stdio oder HTTP  ──▶  Claude
                                 │  (FastMCP)   │
                                 └──────────────┘
```

- `scraper` — `movieplexx scrape --loop`, pollt `POLL_INTERVAL_SECONDS`
  (Default 3600s), upsertet aktuelle Vorstellungen/Filme, hängt pro
  Vorstellung eine History-Zeile an, exponiert Prometheus-Metriken.
- `mcp-server` — `movieplexx serve`, transport-agnostisch (`server.py` kennt
  kein HTTP/stdio), liest read-only.

## 3. Datenquelle

```
GET https://movieplexx.de/programm/api/filtered-films
Accept: application/json
```

Interner JSON-Endpoint der Cineweb-Whitelabel-Plattform, liefert alle
aktuellen Filme mit allen Vorstellungen, Buchungslinks, Formaten und Metadaten
in einem Response. Kein SPA-Scraping, kein Playwright nötig — reiner
HTTP-GET + JSON-Parsing (`scrape.py`).

**Bekannte Lücken in den Rohdaten** (nicht vom Endpoint geliefert):

- Saal (`auditorium_title`) ist durchgehend `null`
- kein konkreter Preis (nur `EUR`/`InStock` im JSON-LD)
- OV/OmU-Kennzeichnung (`original_releases`) meist leer

`raw_json` wird pro Film/Vorstellung roh mitgespeichert, damit Schema-Drift
nicht zu Datenverlust führt — Normalisierung ist idempotent und überspringt
defekte Einzel-Filme statt den ganzen Scrape abzubrechen
(`scrape.normalize`, Feld `parse_errors`).

Legal/Höflichkeit: `/programm` und `/programm/api/*` sind laut robots.txt
nicht disallowed. Selbstidentifizierender User-Agent
(`MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)`), 1 Request/Stunde.

## 4. Datenmodell (SQLite, `store.py`)

```sql
CREATE TABLE performances (
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
-- Indexe: date, film_slug, unixdatetime

CREATE TABLE performance_history (      -- Append-Log, eine Zeile pro Scrape
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
-- Indexe: performance_id, scraped_at, film_slug

CREATE TABLE films (
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
```

Upsert per `ON CONFLICT ... DO UPDATE`, `first_seen` bleibt beim Update
unverändert (Update-Set nimmt sie nicht auf), `last_seen` wird stets
nachgeführt. `performance_history` ist reines Append — daraus lässt sich
Ausverkauft-/Status-Drift über die Zeit rekonstruieren.

## 5. MCP-Tools (`server.py`)

| Tool | Signatur | Zweck |
| --- | --- | --- |
| `list_showtimes` | `(date?, film_slug?, only_upcoming=False)` | Vorstellungen, gefiltert nach ISO-Datum und/oder Slug |
| `get_film` | `(film_slug)` | Volles Film-Record oder `null` |
| `list_films` | `(only_current=True)` | Alle bekannten Filme, optional nur mit künftiger Vorstellung |
| `search_films` | `(query)` | Substring-Suche über Titel/Genre/Regie/Verleih |
| `film_history` | `(film_slug)` | Append-Log der Vorstellungen eines Films |

Alle Tools sind reine `SELECT`s gegen eine `mode=ro`-Connection — kein Tool
schreibt.

## 6. Transport & Deployment

### 6.1 stdio (Default, lokal)

`MCP_TRANSPORT=stdio` (Default). Client startet den Prozess lokal
(`uv run movieplexx serve` bzw. `docker run -i --rm ... serve`).

### 6.2 HTTP (Remote, z.B. NAS)

`MCP_TRANSPORT=http` macht den Server zu einem langlebigen
Streamable-HTTP-Endpoint (`http.py:run_http_server`).

| Variable | Default | Zweck |
| --- | --- | --- |
| `MCP_HOST` | `0.0.0.0` | Bind-Adresse im Container |
| `MCP_PORT` | `8000` | HTTP-Port |
| `MCP_PATH` | `/mcp` | Endpoint-Pfad |
| `MCP_AUTH_TOKEN` | — | **Pflicht.** Ohne Token verweigert `serve` den Start (fail-closed) |
| `MCP_ALLOWED_HOSTS` | — | Kommagetrennte `host:port`-Werte, zusätzlich zu `localhost`/`127.0.0.1`/`::1` |
| `MCP_TLS_CERTFILE` / `MCP_TLS_KEYFILE` | — | Beide zusammen gesetzt → natives TLS-Termination in uvicorn |

**Bearer-Auth:** `BearerAuth`-Middleware vergleicht `Authorization` konstant-zeitig
(`hmac.compare_digest`) gegen `Bearer <MCP_AUTH_TOKEN>`.

**DNS-Rebinding-Schutz:** FastMCP validiert den `Host`-Header über
`TransportSecuritySettings`. Ohne explizite Konfiguration ist das Default
*nur* `127.0.0.1`/`localhost` — deshalb muss `MCP_ALLOWED_HOSTS` die
LAN-Adresse enthalten, unter der Clients den Server ansprechen, sonst
antwortet er mit `421 Invalid Host header` (historischer Bug, siehe §9).

**TLS:** ist im Code vollständig implementiert (`ssl_certfile`/`ssl_keyfile`
an uvicorn durchgereicht, fail-closed bei halb gesetzter Konfiguration), aber
**in der aktuellen NAS-Deployment noch nicht aktiviert** — siehe Roadmap §10.
Ohne TLS läuft der Bearer-Token im Klartext übers LAN.

### 6.3 Docker

Ein Image (`Dockerfile`), zwei Compose-Services:

- `scraper` — `command: ["scrape", "--loop"]`, schreibt in named volume
  `moviedata`, exponiert `METRICS_PORT` (Default 9000)
- `mcp` — `command: ["serve"]`, `MCP_TRANSPORT=http`, mountet `moviedata:ro`,
  `read_only: true` + `tmpfs: /tmp`, Port-Bind explizit auf die NAS-LAN-IP
  (nicht `0.0.0.0` des Hosts)

Secrets (`MCP_AUTH_TOKEN`, `MCP_ALLOWED_HOSTS`) kommen aus einer
gitignoreten `.env` neben der Compose-Datei; beide sind über
`${VAR:?...}` als Pflichtfelder verdrahtet — Compose bricht ohne sie ab.

### 6.4 Image-Publishing (GHCR)

`.github/workflows/docker-publish.yml` baut multiarch
(`linux/amd64`, `linux/arm64`) bei jedem Push auf `main` (Tag `dev`) und bei
jedem GitHub-Release (`X.Y.Z`, `X.Y`, `X`, `latest`) und pusht nach
`ghcr.io/zahlenhelfer/movieplexx-mcp`.

## 7. Betrieb & Observability

Prometheus-Metriken (`metrics.py`), Endpoint `:METRICS_PORT/metrics`
(Default 9000, `<=0` deaktiviert):

- `movieplexx_scrape_success_total` / `..._failure_total`
- `movieplexx_scrape_duration_seconds` (Histogram)
- `movieplexx_films_seen` / `..._performances_seen` (Gauge)
- `movieplexx_parse_errors_total` — Signal für Schema-Drift

Der Scrape-Loop fängt transiente Fehler ab und läuft weiter
(`cmd_scrape`: `except Exception: log.exception(...)`, kein Crash-Loop).

## 8. Tests

- `tests/test_contract.py` — parst einen eingecheckten Golden-Snapshot
  (`tests/fixtures/filtered-films.golden.json`) und prüft die von der
  Normalisierung erwarteten Feldmengen (`FILM_KEYS`/`PERF_KEYS`). Schlägt
  fehl, wenn die Upstream-API driftet; Snapshot wird bei gewollter Drift
  manuell neu gezogen.
- `tests/test_http.py` — `BearerAuth` (fehlender Header, falscher Token,
  fehlendes `Bearer`-Prefix, korrekter Token) sowie `cmd_serve`s
  Transport-Weiche (stdio läuft durch, http ohne Token bricht mit Exit-Code 1
  ab).

## 9. Sicherheitsmodell

- **Fail-closed:** kein `MCP_AUTH_TOKEN` → HTTP-Transport startet nicht.
- **Read-only-Blast-Radius:** alle Tools lesen nur, DB read-only gemountet
  (`mode=ro`) bzw. `read_only: true` + `tmpfs` auf Container-Ebene. Ein
  geleakter Token gibt bestenfalls Lesezugriff auf öffentliche Kinodaten.
- **LAN-only per Default:** Host-Port wird auf die LAN-IP der NAS gebunden,
  kein WAN-Port-Forward.
- **DNS-Rebinding-Schutz** aktiv, per `MCP_ALLOWED_HOSTS` auf die
  tatsächlich genutzte(n) LAN-Adresse(n) beschränkt.
- **Konstant-Zeit-Tokenvergleich** gegen Timing-Angriffe.
- **Bekannter, gelöster Bug:** vor MCP_ALLOWED_HOSTS führte das
  FastMCP-Default (nur localhost erlaubt) zu `421` bei jedem Remote-Request
  über die NAS-LAN-IP — behoben durch die zusätzliche Host-Whitelist statt
  Deaktivieren des Schutzes.
- **Offen:** TLS ist gebaut, aber auf der NAS nicht aktiviert (§10) — bis
  dahin geht der Bearer-Token im Klartext übers LAN.

## 10. Roadmap / Offene Punkte

Reihenfolge nach Aufwand, nicht nach Priorität:

1. **TLS in Produktion aktivieren** — `.env` auf der NAS um
   `MCP_TLS_CERTFILE`/`MCP_TLS_KEYFILE` ergänzen (Zertifikat liegt bereits
   lokal vor, `CN=192.168.2.231`), Client-Config auf `https://` umstellen,
   Smoke-Test wiederholen.
2. **`get_price_table`-Tool** — Preistabelle einmalig von
   `/information/service-kontakt/oeffnungszeiten-preise` scrapen und als
   statisches Tool ausliefern (in §8 des Vorgänger-Dokuments geplant, nie
   gebaut).
3. **Off-LAN-Zugriff** — Tailscale/WireGuard vor die NAS; Transport/Auth
   bleiben unverändert, nur die Client-URL ändert sich.
4. **Öffentliche Exposition** — falls je nötig: Reverse-Proxy mit
   Rate-Limiting davor, zusätzlich zum bestehenden Bearer-Token.
5. **K8s-Manifeste** — `CronJob` für den Scraper, `Deployment` für den
   HTTP-MCP-Server, `PersistentVolumeClaim` bzw. Wechsel auf Postgres bei
   ernsthafter Historisierung. Nur relevant, falls das Ziel-Deployment
   Richtung Cluster statt NAS geht.
6. **OAuth/OIDC** — nur sinnvoll bei Multi-User- oder öffentlichem Betrieb;
   für den aktuellen Single-User-LAN-Kontext Overkill.

## 11. Quellen

Site-Recon (Endpoint-Schema, robots.txt, URL-Struktur) durchgeführt am
2026-07-07 gegen die Live-Site movieplexx.de; Details dazu in der
Git-Historie dieses Dokuments (`git log -p -- spec.md`).
