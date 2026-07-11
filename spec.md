# MCP-Movieplexx-Scraping-Plan

Stand: 2026-07-07 · Ziel: MCP-Server, der das aktuelle Kinoprogramm des Movieplexx Buchholz spiegelt und historisch archiviert.

## Executive Summary

Die Movieplexx-Seite ist **kein SPA**, sondern eine server-rendered Laravel-Blade-Site auf der **Cineweb**-Whitelabel-Plattform mit einer Vue-basierten Timetable-Komponente obendrauf. Der Content der Programm-Seite ist als JSON-LD `ScreeningEvent` bereits im initial-HTML enthalten — und noch besser: die Vue-Komponente zieht ihre Daten aus einem eigenen JSON-Endpoint `https://movieplexx.de/programm/api/filtered-films`, der **alle Filme mit allen Vorstellungen, Buchungslinks, Formaten, FSK, Cast, Trailern und Metadaten in einem einzigen Response** liefert. Der Aufwand ist damit klein: reiner HTTP-Client + JSON-Parsing + SQLite, kein Playwright, kein DOM-Parsing. Realistisch **1 Wochenende bis MVP**, weitere 1–2 Tage für saubere Docker-/Compose-Verpackung und MCP-Server-Anbindung.

Die frühere Vermutung "SPA / leerer Body" beruhte auf einer nicht-existierenden URL (`/de/kino/buchholz`). Movieplexx hat nur einen Standort und nutzt Root-Pfade wie `/programm` und `/programm/film/<slug>`. Dieser Punkt ist damit erledigt.

---

## 1. Site-Recon — Findings

### Tech-Stack (verifiziert)

| Ebene | Beobachtung | Beweis |
| --- | --- | --- |
| CMS/Framework | Laravel-Blade (PHP) | Debug-Reste im HTML: `collect($socialLink)->get('title')` als Alt-Text |
| Front-End | Vue.js (nur für Timetable-Widget) | `data-v-app`, `data-v-128058a0`-Scope-Marker; separates JS-Bundle `theme/solar/js/vue-schedule.js` |
| Plattform | **Cineweb** (Whitelabel-Anbieter) | Footer: „Ein Partner von cineweb.de"; Assets liegen auf `cdn.cineweb.de`; Tracking-Pixel `dispatcher.cineweb.eu/host/movieplexx.de/city/433/pixel.png` (city-ID `433`) |
| Ticketing-Backend | **kinotickets.express** / **kinotickets.online** (Cinuru) | Alle Buchungs-Deep-Links gehen auf `kinotickets.express/movieplex-buchholz/booking/<performanceID>`; robots.txt sperrt `/cinuru` |
| Rendering-Modus | **SSR mit Progressive-Enhancement**, kein SPA | HTML-Länge Programm-Seite: 186 kB, JSON-LD ist im initial-HTML enthalten, ohne JS bereits vollständig sichtbar |

### URL-Struktur

| Pfad | Zweck |
| --- | --- |
| `https://movieplexx.de/` | Startseite (Marketing) |
| `https://movieplexx.de/programm` | Wochenprogramm-Übersicht (SSR + JSON-LD + Vue) |
| `https://movieplexx.de/programm/film/<slug>` | Film-Detail mit Timetable |
| `https://movieplexx.de/programm/api/filtered-films` | **Interne JSON-API** — der Hauptfund |
| `https://movieplexx.de/programm/api/filtered-films?slugs=<slug>` | Detail einzelner Film |
| `https://movieplexx.de/vorschau` | Kommende Filme |
| `https://movieplexx.de/aktionen-events` | Sonderveranstaltungen |
| `https://kinotickets.express/movieplex-buchholz/booking/<perfID>` | Sitzplatzauswahl (Cinuru) |

Anmerkung: URLs wie `/programm#filter/alle/2026-07-25/alle/alle/alle/alle` sind Client-Hash-Router-Fragmente der Vue-Komponente. Server ignoriert sie — die Filterung passiert im JSON-Endpoint über Query-Parameter, siehe unten.

### robots.txt

```
User-agent: *
Disallow: /intern
Disallow: /cinuru
Disallow: /export
```

**Für unser Scraping-Ziel `/programm` und `/programm/api/*` gibt es keine Einschränkung.** `sitemap.xml` liefert nichts Nennenswertes (leerer Body).

### Was WebFetch initial vergessen hat

Ein WebFetch auf `/de/kino/buchholz` lieferte leeren Body — nicht weil es ein SPA ist, sondern weil diese URL **nicht existiert**. Der Roh-Fetch auf `/` und `/programm` liefert vollständiges HTML.

---

## 2. Scraping-Plan — Fall A: JSON-API (empfohlen)

### Der Endpoint

```
GET https://movieplexx.de/programm/api/filtered-films
Accept: application/json
```

Ohne Query-Parameter liefert der Endpoint **alle aktuellen Filme des Kinos** in einem Rutsch. Getestet am 2026-07-07: **20 Filme, 65 Vorstellungen** (ca. 150 kB Response).

Optionale Query-Parameter (aus `data.filters`-Struktur ableitbar):

| Param | Werte | Zweck |
| --- | --- | --- |
| `slugs` | Film-Slug (kommasepariert) | Einzelfilm-Detail |
| `series` | `filmkunst-matinee`, `woman-night`, `andre-rieu` etc. | Reihen-Filter |
| `date` | `heute`, `morgen`, ISO-Datum | Datumsfilter |
| `release` | `2D`, `3D`, `OV`, `OmU` | Format |
| `cinema` | site-ID | mehrere Standorte (bei Movieplexx irrelevant, nur `469`) |
| `auditorium` | Saal-Slug | Saal-Filter |
| `fsk` | FSK-Wert | FSK-Filter |

Für unseren MVP: **kein Parameter** — wir wollen alles.

### Response-Schema (Kern)

```jsonc
{
  "totalCount": 20,
  "films": [
    {
      "filmTitle": "Minions & Monster",
      "detailId": 403866,
      "slug": "minions-monster",
      "fsk": "6",
      "length": "90",
      "length_hours": 1, "length_minutes": 30,
      "genre": "Animation, Familienfilm",
      "country": "USA",
      "distributor": "Universal Int'l",
      "castAndCrew": { "Regie": "Pierre Coffin" },
      "descriptor": "Bedrohung, belastende Szenen",
      "teaser": "...", "shortText": "...", "text": "...",
      "trailer": "...", "trailerAvailable": true,
      "filmReleases": { "2D": "2D", "3D": "3D" },
      "firstPerformance": "...", "lastPerformance": "...",
      "url": "/programm/film/minions-monster",
      "poster": "...",
      "performances": [
        {
          "siteId": 469, "siteName": "Movieplexx",
          "performances": {
            "33644": {
              "performanceID": 33644,
              "date": "2026-07-08",
              "time": "15:00:00",
              "unixdatetime": 1783515600,
              "releases": {"2D": "2D"},
              "releasesCombined": ["2D"],
              "originalReleases": "",
              "status": "normal",
              "bookingLink": "https://kinotickets.express/movieplex-buchholz/booking/33644",
              "isOnline": 1, "saleIsAllowed": 1,
              "isSoldOut": 0, "isNotBookable": 0,
              "performanceAuditoriumAttributeTitle": null,
              "performanceType": "film",
              "uniqueUnixdatetime": "1783515600_33644"
            }
          }
        }
      ]
    }
  ],
  "filters": { "series": {...}, "date": {...}, "release": {...}, "auditorium": {...}, "fsk": {...} },
  "config": { "city": ..., "cdn": ..., ... }
}
```

### Real geloggter Sample-Event (aus einem Live-Call am 2026-07-07)

```json
{
  "performance_id": 33644,
  "film_title": "Minions & Monster",
  "film_slug": "minions-monster",
  "fsk": "6",
  "length_min": "90",
  "date": "2026-07-08",
  "time": "15:00:00",
  "unixdatetime": 1783515600,
  "releases": "2D",
  "is_sold_out": false,
  "is_online": true,
  "booking_link": "https://kinotickets.express/movieplex-buchholz/booking/33644",
  "site_id": 469,
  "auditorium_title": null,
  "performance_type": "film",
  "original_releases": ""
}
```

### Was liefert der Endpoint NICHT

- **Saal (`performanceAuditoriumAttributeTitle`)**: aktuell `null` für alle 65 Vorstellungen. Der Filter kennt zwar `auditorium`, aber das Attribut wird nach außen offenbar nicht befüllt. Sitzplatzinfo/Saal-Layout sind ausschließlich im Buchungs-Flow (`kinotickets.express/booking/<id>`) sichtbar.
- **Konkreter Preis**: JSON-LD sagt nur `priceCurrency: EUR`, `availability: InStock`. Die tatsächliche Preistabelle steht im Cinuru-Buchungsflow (dort auch Ermäßigungen, Kinderpreis, 3D-Aufschlag).
- **OV/OmU-Kennzeichnung**: `originalReleases` war in unserem Sample leer — evtl. wird das Feld nur bei Filmen mit OV-Vorstellungen befüllt. Robust behandeln.

### Fall B (SPA) und Fall C (Hybrid) — nicht relevant

Da Fall A verifiziert funktioniert, brauchen wir weder Playwright noch DOM-Parsing. Falls die interne API kommentarlos wegfällt (Restrisiko, siehe §7), fallback auf JSON-LD-Parsing der `/programm`-HTML-Seite: die enthält alle `ScreeningEvent`-Objekte ebenfalls (65 Stück verifiziert), allerdings **ohne** `performanceID` und `bookingLink` — dann müssten Buchungslinks über Filmdetail-Seiten mit Selektor-Parsing rekonstruiert werden.

---

## 3. Sprachentscheidung: **Python**

Beide Sprachen können den Job. Meine Empfehlung ist Python, mit klaren Gegenargumenten für TypeScript falls der Team-Standard anders liegt.

| Kriterium | Python | TypeScript (Node) |
| --- | --- | --- |
| MCP-SDK-Reife | `mcp` (offiziell, sehr aktiv, viele Beispiele) | `@modelcontextprotocol/sdk` (offiziell, auch stabil) |
| Scraping-Deps | `httpx` (async, HTTP/2) — sehr klein | `undici` (nativ ab Node 18) — auch sehr klein |
| SQLite | `sqlite3` in stdlib, `aiosqlite` optional | `better-sqlite3` (native compile) oder `libsql` |
| Docker-Image | `python:3.12-slim` ~50 MB Base, mit Deps 120–150 MB | `node:22-alpine` ~40 MB, mit Deps 90–120 MB |
| Marcus' Kontext | K8s-Trainer — Python allgegenwärtig in Operator/Cluster-Tools | Angular-Background — TS-Kontext natürlicher |
| Cold-Start / Latenz | Höher (Interpreter-Load) | Niedriger |
| Debugging | Auf Servern und in K8s vertraut | Genauso ok |

**Empfehlung: Python**, weil (a) das MCP-Python-SDK aktuell mehr Beispiele und Server-Templates liefert, (b) `pydantic` das Normalisierungs-Schema geradezu verschenkt, (c) im DevOps-Kontext eher Python-Tooling erwartet wird (Ansible-Nähe, K8s-CRD-Skripting).

**TS ist eine legitime Alternative** und würde ich empfehlen falls: das MCP-Server-Ökosystem, in dem er läuft, bereits Node-lastig ist; oder falls der Angular-Kontext auch ein späteres Web-Dashboard nahelegt und du das TS-Schema teilen willst.

---

## 4. Docker-Layout

### Architektur (Variante A festgezurrt)

```
┌────────────────┐   Schedule    ┌──────────────┐
│  scraper (CLI) │──────────────▶│  SQLite-DB   │
│  supercronic   │               │  (Volume)    │
└────────────────┘               └──────┬───────┘
                                        │ read-only
                                        ▼
                                 ┌──────────────┐
                                 │  mcp-server  │  stdio  ──▶  Claude-Client
                                 │  (fastmcp)   │
                                 └──────────────┘
```

Zwei Container aus **einem Image**, unterschiedlicher `CMD`:
- `scrape` — pollt periodisch, upsertet aktuelle Vorstellungen, schreibt Append-Log
- `serve` — startet MCP-Server (stdio oder HTTP/SSE), liest read-only aus derselben DB

### Datenmodell (SQLite)

```sql
-- Aktueller Stand: eine Zeile pro (Kino, Vorstellung)
CREATE TABLE performances (
  performance_id     INTEGER PRIMARY KEY,   -- 33644
  film_slug          TEXT NOT NULL,
  film_title         TEXT NOT NULL,
  fsk                TEXT,
  length_min         INTEGER,
  date               TEXT NOT NULL,          -- ISO 2026-07-08
  time               TEXT NOT NULL,          -- 15:00:00
  unixdatetime       INTEGER NOT NULL,
  releases           TEXT,                   -- "2D" | "3D" | "OmU" | ...
  original_releases  TEXT,
  is_online          INTEGER NOT NULL,
  is_sold_out        INTEGER NOT NULL,
  is_not_bookable    INTEGER NOT NULL,
  booking_link       TEXT,
  auditorium_title   TEXT,
  site_id            INTEGER NOT NULL,
  first_seen         TEXT NOT NULL,          -- ISO
  last_seen          TEXT NOT NULL,          -- ISO — für „verschwundene Vorstellungen" 
  raw_json           TEXT NOT NULL           -- vollständiges Original-Objekt
);
CREATE INDEX idx_perf_date ON performances(date);
CREATE INDEX idx_perf_slug ON performances(film_slug);
CREATE INDEX idx_perf_unix ON performances(unixdatetime);

-- Append-Log: jeder Scrape ergibt einen neuen Snapshot pro Vorstellung
CREATE TABLE performance_history (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  performance_id     INTEGER NOT NULL,
  scraped_at         TEXT NOT NULL,
  is_sold_out        INTEGER,
  is_online          INTEGER,
  status             TEXT,
  releases           TEXT,
  film_title         TEXT,
  raw_json           TEXT NOT NULL
);
CREATE INDEX idx_hist_perf ON performance_history(performance_id);
CREATE INDEX idx_hist_time ON performance_history(scraped_at);

-- Filme (dimensional)
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
  first_seen      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  raw_json        TEXT NOT NULL
);
```

Upsert-Logik: für jede Vorstellung `INSERT ... ON CONFLICT(performance_id) DO UPDATE SET last_seen=..., is_sold_out=..., ...`, danach unabhängig eine Zeile in `performance_history`. Damit hast du beides: aktuellen Snapshot **und** vollständige Zeitreihe (Ausverkaufszustand, Format-Änderungen, Cancellations).

### Multi-Stage-Dockerfile (Python)

```dockerfile
# syntax=docker/dockerfile:1.7

# ── Stage 1: Builder ────────────────────────────────────────
FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ── Stage 2: Runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DB_PATH=/data/movieplexx.db \
    TARGET_URL=https://movieplexx.de/programm/api/filtered-films \
    POLL_INTERVAL_SECONDS=3600 \
    USER_AGENT="MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)" \
    LOG_LEVEL=INFO

# supercronic für PID-1-safe Cron (statisches Binary, ~7 MB)
ADD --chmod=755 https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64 /usr/local/bin/supercronic

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app \
 && mkdir -p /data && chown -R app:app /data
WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY src/ ./src/
COPY crontab /app/crontab

ENV PATH="/app/.venv/bin:$PATH"
VOLUME ["/data"]
USER app

# CMD wird von docker-compose überschrieben
ENTRYPOINT ["/bin/sh", "-c"]
CMD ["python -m movieplexx.cli serve"]
```

Erwartete Image-Größe: **ca. 130–150 MB komprimiert**. Der Löwenanteil sind Python + httpx + pydantic. Wenn du das noch drücken willst: Wechsel auf `python:3.12-alpine` (spart 30 MB, aber Musl-Kompatibilitätsrisiko bei Wheels — für httpx/pydantic aber unkritisch).

### `docker-compose.yml`

```yaml
services:
  scraper:
    build: .
    command: ["python -m movieplexx.cli scrape --loop"]
    environment:
      POLL_INTERVAL_SECONDS: "3600"     # 1x pro Stunde
      USER_AGENT: "MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)"
      LOG_LEVEL: INFO
    volumes:
      - moviedata:/data
    restart: unless-stopped
    # Falls du Cron statt Loop willst:
    # command: ["supercronic /app/crontab"]

  mcp:
    build: .
    command: ["python -m movieplexx.cli serve"]
    stdin_open: true
    tty: true
    read_only: true
    volumes:
      - moviedata:/data:ro
      - /tmp     # writable tmp
    depends_on: [scraper]
    # In der Praxis wird der MCP-Server oft per `docker run -i --rm mcp-image serve`
    # aus dem Claude-Client-Config heraus gestartet. Der Compose-Eintrag ist v.a. für
    # SSE-basierte MCP-Deployments sinnvoll.

volumes:
  moviedata: {}
```

Beispiel-crontab (falls du supercronic statt Python-Loop willst):

```
# jede Stunde zur Minute 3
3 * * * * python -m movieplexx.cli scrape
```

Scheduler-Empfehlung: **Python-Loop bei einem einzigen Job** (weniger Moving-Parts), **supercronic bei mehreren Jobs** (z.B. Preview-Scrape + Programm-Scrape + Reihen-Scrape). Externer K8s-CronJob ist im Compose-Kontext overkill, wäre aber in K8s die kanonische Lösung — ein passendes `CronJob`-Manifest ist mit dem `scrape`-CMD trivial abzuleiten.

---

## 5. Prototyp-Snippet (Python, verifiziert)

Getestet am 2026-07-07 gegen den Live-Endpoint, liefert 65 Vorstellungen aus 20 Filmen.

```python
# src/movieplexx/scrape.py  (Ausschnitt, ~20 Zeilen)
import httpx, json, sys
from datetime import datetime, timezone

UA  = "MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)"
URL = "https://movieplexx.de/programm/api/filtered-films"

def fetch_program() -> list[dict]:
    r = httpx.get(URL, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=20.0)
    r.raise_for_status()
    data = r.json()
    now = datetime.now(timezone.utc).isoformat()
    events = []
    for film in data["films"]:
        for group in film.get("performances") or []:
            for pid, p in (group.get("performances") or {}).items():
                events.append({
                    "performance_id":   p["performanceID"],
                    "film_slug":        film["slug"],
                    "film_title":       film["filmTitle"],
                    "fsk":              film.get("fsk"),
                    "date":             p["date"],
                    "time":             p["time"],
                    "unixdatetime":     p["unixdatetime"],
                    "releases":         ",".join(p.get("releasesCombined") or []),
                    "is_sold_out":      bool(p.get("isSoldOut")),
                    "is_online":        bool(p.get("isOnline")),
                    "booking_link":     p.get("bookingLink"),
                    "site_id":          p.get("siteId"),
                    "auditorium":       p.get("performanceAuditoriumAttributeTitle"),
                    "scraped_at":       now,
                })
    return events

if __name__ == "__main__":
    events = fetch_program()
    print(f"Gefunden: {len(events)} Vorstellungen", file=sys.stderr)
    print(json.dumps(events[0], indent=2, ensure_ascii=False))
```

Live-Output der ersten Vorstellung:

```json
{
  "performance_id": 33644,
  "film_slug": "minions-monster",
  "film_title": "Minions & Monster",
  "fsk": "6",
  "date": "2026-07-08",
  "time": "15:00:00",
  "unixdatetime": 1783515600,
  "releases": "2D",
  "is_sold_out": false,
  "is_online": true,
  "booking_link": "https://kinotickets.express/movieplex-buchholz/booking/33644",
  "site_id": 469,
  "auditorium": null
}
```

### MCP-Server-Skelett (`fastmcp`)

```python
# src/movieplexx/server.py
from mcp.server.fastmcp import FastMCP
import sqlite3, os

mcp = FastMCP("movieplexx-buchholz")
DB  = os.environ["DB_PATH"]

def _conn():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

@mcp.tool()
def list_showtimes(date: str | None = None, film_slug: str | None = None) -> list[dict]:
    """Liefert Vorstellungen. Optional gefiltert nach ISO-Datum oder Film-Slug."""
    q = "SELECT performance_id, film_title, film_slug, date, time, releases, is_sold_out, booking_link FROM performances WHERE 1=1"
    args = []
    if date:      q += " AND date = ?";      args.append(date)
    if film_slug: q += " AND film_slug = ?"; args.append(film_slug)
    q += " ORDER BY unixdatetime"
    with _conn() as c:
        return [dict(zip([col[0] for col in c.execute(q, args).description],
                         row)) for row in c.execute(q, args)]

@mcp.tool()
def film_history(film_slug: str) -> list[dict]:
    """Historische Vorstellungen eines Films (Append-Log)."""
    with _conn() as c:
        rows = c.execute("""
            SELECT scraped_at, date, time, is_sold_out
              FROM performance_history WHERE film_slug = ?
             ORDER BY scraped_at
        """, [film_slug])
        return [dict(zip([col[0] for col in rows.description], row)) for row in rows]

if __name__ == "__main__":
    mcp.run()  # stdio
```

---

## 6. Legalitäts- und Höflichkeits-Check

### robots.txt

```
User-agent: *
Disallow: /intern
Disallow: /cinuru
Disallow: /export
```

`/programm` und `/programm/api/*` sind **nicht disallowed** — Scraping ist damit robots-konform. Zusätzlich zu prüfen: das AGB-/Datenschutz-Dokument des Betreibers (`https://movieplexx.de/rechtliches/agb`), Verwertungsklauseln für die Programm-Daten. Da wir nur öffentliches, nicht personenbezogenes Programm speichern, sehe ich keinen materiellen Konflikt — für den Betrieb im Firmenkontext wäre trotzdem eine kurze schriftliche Abstimmung mit dem Kino sinnvoll (die Programmdaten stammen letztlich vom Filmverleih, das Kino ist Sub-Lizenznehmer).

### Rate-Limit-Empfehlung

Das Kino sagt auf `/programm` selbst: „Das Programm für die Kinowoche (Donnerstag bis Mittwoch) wird Montags erstellt und ist ab Montagmittag verfügbar." Änderungen darüber hinaus sind selten (Ausverkauft-Status, Ergänzungen für Sondertermine).

Konservativ: **max. 1 Request pro Stunde** deckt alle sinnvollen Aktualisierungen ab und ist gleichzeitig ein Bruchteil dessen, was ein einzelner Website-Nutzer über den Tag generiert. Absolute Untergrenze (falls Realtime-Ausverkauft-Signal gewünscht): **max. 1 Request pro 5 Minuten**. Alles darunter ist unhöflich und lädt zum Bannen ein.

### User-Agent

Selbstidentifizierend, mit Kontaktadresse:

```
User-Agent: MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)
```

Empfehlung: **keinen Browser-UA vortäuschen.** Das erschwert dem Betreiber die Kontaktaufnahme im Konfliktfall und ist im Grenzbereich zu unfreundlich.

### Zusätzliche Höflichkeit

- `If-Modified-Since` senden, sobald bekannt (Endpoint scheint das aktuell nicht zu unterstützen — testen).
- HTTP/2 mitnutzen (httpx macht das automatisch mit `h2`-Extra).
- Exponential Backoff bei 5xx, mindestens 60 s Basis.
- Alerting bei Schema-Drift (siehe §7).

---

## 7. Restrisiken

| Risiko | Wahrscheinlichkeit | Auswirkung | Gegenmaßnahme |
| --- | --- | --- | --- |
| **Interne API verschwindet oder wird umbenannt** | mittel | hoch | JSON-LD-Fallback (Programm-Seite HTML → `ScreeningEvent`); dann fehlt `performanceID`/`bookingLink`, aber Zeitplan bleibt |
| **Schema-Drift** (Feldrename in `performances` / `films`) | mittel-hoch (interne API!) | mittel | `raw_json` roh in DB behalten, Normalisierung idempotent halten, Prometheus-Zähler für Parse-Fehler + Alert bei > 0 |
| **Rate-Limit oder Cloudflare-Wall** | niedrig aktuell | hoch | Ehrlicher UA + 1 req/h reduziert Risiko drastisch; bei Auftreten Kontaktaufnahme mit Betreiber |
| **Layout-/Feld-Änderungen bei Cineweb-Whitelabel** | Cineweb-Releases geschätzt monatlich, breaking changes eher quartalsweise | mittel | Contract-Tests: golden JSON aus einem Snapshot einchecken, Regressionstest vor jedem Deployment |
| **Zeitzonen-Bug** (`unixdatetime` vs. lokaler `time`) | niedrig | mittel | Immer `unixdatetime` als Source-of-Truth speichern, `time` nur als Anzeigefeld |
| **`auditorium_title` bleibt null** | Beobachtete Realität | niedrig | Feature bewusst als „nicht verfügbar" dokumentieren; wer Saal-Info braucht, muss den Cinuru-Buchungsflow (nicht disallowed, aber deutlich fragiler) auslesen |
| **Preisdaten fehlen** | Beobachtete Realität | niedrig-mittel | Preistabelle einmalig aus `/information/service-kontakt/oeffnungszeiten-preise` scrapen und als statische Tabelle mitliefern; MCP-Tool `get_price_table` |
| **OV/OmU-Kennung** | Feld beobachtet aber leer | niedrig | `original_releases` roh übernehmen, im Zweifel als leer behandeln |
| **Cinuru/kinotickets.express als Fallback** | robots.txt: `/cinuru` disallowed auf **movieplexx.de**, aber `kinotickets.express` ist andere Domain | mittel | Vor jeder Nutzung von `kinotickets.express` deren `robots.txt` separat prüfen |

### Alternativ-Pfade falls Fall A hart bricht

1. **JSON-LD aus `/programm`-HTML parsen** — kein Playwright nötig, `selectolax`/`lxml` reicht. Verlust: `performanceID`, `bookingLink`, `isSoldOut`. Gewinn: absolut stabil, weil schema.org-konformes Markup.
2. **cineweb.de kontaktieren** — die Whitelabel-Plattform könnte auf Anfrage einen offiziellen Feed bereitstellen. Realistisch nur bei kommerziellem Interesse.
3. **kinoheld.de / cinuru.com direkt** — Movieplexx Buchholz ist über `kinotickets.express/movieplex-buchholz` erreichbar. Deren interne API (`movies`/`sale/*`) reverse-zu-engineeren ist aufwendiger und weniger höflich als der bereits gefundene Endpoint auf movieplexx.de selbst.

---

## 8. Empfohlene Reihenfolge der Umsetzung

1. **`scrape.py`** minimal, Endpoint-Call + Normalisierung + Print (existiert oben)
2. **`store.py`** mit SQLite-Schema + Upsert + Append-Log
3. **`cli.py`** mit `scrape`, `scrape --loop`, `serve`
4. **`server.py`** mit `fastmcp` — Tools: `list_showtimes`, `get_film`, `film_history`, `search_films`, `get_price_table`
5. **Dockerfile + docker-compose.yml**
6. **Contract-Test**: einen Golden-Snapshot der API einchecken, in CI parsen, Fehler auf Schema-Drift
7. **Prometheus-Metriken** (optional, aber im DevOps-Kontext natürlich): `movieplexx_scrape_success_total`, `..._duration_seconds`, `..._films_seen`, `..._performances_seen`, `..._parse_errors_total`
8. **K8s-Manifests** falls Ziel Cluster: `CronJob` für Scrape, `Deployment` mit HTTP/SSE-MCP-Endpoint, `PersistentVolumeClaim` für die DB (oder Postgres-`StatefulSet` bei ernsthafter Historisierung)

---

## 9. Quellen der Recon

- `https://movieplexx.de/` — Startseite, SSR-HTML voll enthalten
- `https://movieplexx.de/programm` — 65 `ScreeningEvent` in JSON-LD embedded
- `https://movieplexx.de/programm/film/supergirl` — Beispiel-Filmdetail, 8 Screenings
- `https://movieplexx.de/programm/api/filtered-films` — **Haupt-Endpoint**, 20 Filme / 65 Vorstellungen, 150 kB JSON
- `https://movieplexx.de/robots.txt` — geprüft, `/programm/*` erlaubt
- Network-Trace via Chrome DevTools (Vue-Bundle: `theme/solar/js/vue-schedule.js`) — bestätigt, dass die interne API der Datenlieferant der Timetable ist

Alle Fetches durchgeführt am 2026-07-07 gegen die Live-Site.

---

## 10. Feature: Remote-Serving (HTTP-Transport auf NAS)

Stand: 2026-07-11 · Ziel: den MCP-Server dauerhaft auf einem NAS (Docker) laufen
lassen und vom lokalen Claude (Claude Code **und** Claude Desktop) über das
LAN erreichen — ohne pro Anfrage einen lokalen Prozess/Container zu starten.

### 10.1 Ausgangslage und Kernänderung

Aktuell spricht der Server **ausschließlich stdio** (`mcp.run()`): der Client
startet den Prozess lokal (`uv run movieplexx serve` bzw. `docker run -i …`).
Für den NAS-Betrieb ist das ungeeignet — der Server muss **langlebig über das
Netz** erreichbar sein. Die MCP-Spezifikation sieht dafür den **Streamable-HTTP**
-Transport vor (löst das ältere SSE ab). FastMCP kann diesen Transport direkt
bereitstellen.

**Entscheidung:** HTTP ist **additiv**. stdio bleibt Default (lokale Entwicklung,
bestehende Client-Configs unverändert). Der Transport wird per Env-Variable
gewählt.

Netzmodell: **LAN-only**. Auth: **statischer Bearer-Token**. Deployment:
**generisches docker-compose**. Clients: **Claude Code + Claude Desktop**.

### 10.2 Neue Konfiguration (Environment)

| Variable | Default | Zweck |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` | `stdio` \| `http` — wählt den Transport |
| `MCP_HOST` | `0.0.0.0` | Bind-Adresse im Container (Host-Mapping begrenzt die Exposition) |
| `MCP_PORT` | `8000` | HTTP-Port |
| `MCP_PATH` | `/mcp` | Endpoint-Pfad des Streamable-HTTP-Servers |
| `MCP_AUTH_TOKEN` | — | **Pflicht bei `http`.** Shared Secret für `Authorization: Bearer`. Fehlt er → Start wird verweigert (fail-closed) |

### 10.3 Server-/CLI-Änderungen

`server.py` bleibt inhaltlich unverändert (Tools sind transport-agnostisch, die
DB-Verbindung ist bereits read-only pro Aufruf → mehrfach-parallele
HTTP-Requests unkritisch). Neu ist nur die Transport-Wahl in `cli.py serve` plus
eine Bearer-Middleware.

```python
# src/movieplexx/http.py  (neu) — Bearer-Auth als ASGI-Middleware
import hmac
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class BearerAuth(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self._expected = f"Bearer {token}"
    async def dispatch(self, request, call_next):
        header = request.headers.get("authorization", "")
        # constant-time: verhindert Timing-Leak des Tokens
        if not hmac.compare_digest(header, self._expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
```

```python
# src/movieplexx/cli.py  (Ausschnitt: serve)
import os, sys, uvicorn
from .server import mcp
from .http import BearerAuth

def serve() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()                                   # unverändertes Verhalten
        return
    if transport == "http":
        token = os.getenv("MCP_AUTH_TOKEN")
        if not token:                               # fail-closed
            sys.exit("MCP_AUTH_TOKEN is required for MCP_TRANSPORT=http")
        app = mcp.streamable_http_app()             # Starlette-App von FastMCP
        app.add_middleware(BearerAuth, token=token)
        uvicorn.run(
            app,
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8000")),
        )
        return
    sys.exit(f"unknown MCP_TRANSPORT: {transport!r}")
```

Abhängigkeiten: `uvicorn` (kommt i.d.R. transitiv über das `mcp`-SDK; sonst
explizit in `pyproject.toml` aufnehmen). `starlette` wird von FastMCP ohnehin
gezogen.

### 10.4 docker-compose (NAS)

Der `mcp`-Service wird vom stdio-On-Demand-Container zum **langlebigen,
netzgebundenen** Service. Port-Mapping **auf die LAN-IP der NAS** binden (nicht
`0.0.0.0` des Hosts), damit der Endpoint nicht versehentlich über andere
Interfaces/WAN erreichbar ist.

```yaml
services:
  scraper:
    image: ghcr.io/zahlenhelfer/movieplexx-mcp:latest
    command: ["python -m movieplexx.cli scrape --loop"]
    environment:
      POLL_INTERVAL_SECONDS: "3600"
    volumes:
      - moviedata:/data
    restart: unless-stopped

  mcp:
    image: ghcr.io/zahlenhelfer/movieplexx-mcp:latest
    command: ["python -m movieplexx.cli serve"]
    environment:
      MCP_TRANSPORT: http
      MCP_HOST: 0.0.0.0
      MCP_PORT: "8000"
      MCP_AUTH_TOKEN: ${MCP_AUTH_TOKEN:?set MCP_AUTH_TOKEN in .env}
    ports:
      - "192.168.1.50:8000:8000"   # NUR an die LAN-IP der NAS binden
    read_only: true
    volumes:
      - moviedata:/data:ro
      - /tmp
    depends_on: [scraper]
    restart: unless-stopped

volumes:
  moviedata: {}
```

Token wird in einer **gitignore-ten `.env`** neben der compose-Datei gehalten:

```
MCP_AUTH_TOKEN=$(openssl rand -hex 32)
```

### 10.5 Client-Anbindung (lokaler Claude)

**Claude Code (CLI)** — nativer HTTP-Transport:

```bash
claude mcp add --transport http movieplexx http://192.168.1.50:8000/mcp \
  --header "Authorization: Bearer <TOKEN>"
```

**Claude Desktop** — kein nativer Remote-HTTP-Client, daher die
`mcp-remote`-Bridge (stdio ⇄ HTTP) in `claude_desktop_config.json`. Den
kompletten Header über eine Env-Variable setzen, um das bekannte
Whitespace-Splitting bei `--header` zu umgehen:

```json
{
  "mcpServers": {
    "movieplexx": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://192.168.1.50:8000/mcp",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": { "AUTH_HEADER": "Bearer <TOKEN>" }
    }
  }
}
```

### 10.6 Sicherheits-Überlegungen (LAN-Kontext)

- **Fail-closed:** ohne `MCP_AUTH_TOKEN` startet der HTTP-Transport nicht.
- **Read-only-Blast-Radius:** alle Tools lesen nur; die DB ist `mode=ro`
  gemountet. Selbst bei Token-Leak im LAN ist der Schaden auf Lesen öffentlicher
  Kinodaten begrenzt.
- **LAN-Bindung:** Host-Port an die NAS-LAN-IP binden; **kein** WAN-Port-Forward.
  Soll es später von außen erreichbar sein → §10.7.
- **DNS-Rebinding / Origin:** Streamable-HTTP-Server sollten `Host`/`Origin`
  validieren. FastMCP bringt dafür eine Transport-Security-Middleware mit —
  erlaubte Hosts/Origins auf die NAS-IP/den Hostnamen beschränken.
- **Constant-time-Vergleich** des Tokens (`hmac.compare_digest`) gegen
  Timing-Angriffe.
- **Rotation:** Token = Env-Var; Rotation = `.env` ändern, `mcp`-Service neu
  starten, Client-Header aktualisieren.

### 10.7 Ausbaustufen (nicht Teil dieses Features)

- **Off-LAN-Zugriff:** Tailscale/WireGuard vor die NAS setzen — Client zeigt
  dann auf die Tailnet-IP, Transport/Auth bleiben unverändert.
- **Öffentliche Exposition:** Reverse-Proxy (Caddy/Traefik) mit TLS + echtem
  Zertifikat davor; Token-Auth bleibt, zusätzlich Rate-Limit.
- **OAuth/OIDC:** nur bei Multi-User-/öffentlichem Betrieb sinnvoll.

### 10.8 Umsetzungs-Checkliste

1. `src/movieplexx/http.py` mit `BearerAuth`-Middleware anlegen.
2. `cli.py serve` um die Transport-Weiche (`MCP_TRANSPORT`) erweitern.
3. `uvicorn` in `pyproject.toml` sicherstellen.
4. Neue Env-Vars in Dockerfile-Defaults (nur unkritische wie `MCP_TRANSPORT`,
   `MCP_PORT`, `MCP_PATH`) und in der README dokumentieren.
5. `docker-compose.yml` um den netzgebundenen `mcp`-Service + `.env`-Muster
   ergänzen; `.env` in `.gitignore`.
6. README: Abschnitt „Remote-Serving auf NAS" inkl. beider Client-Configs.
7. Smoke-Test: `curl` ohne Token → 401, mit Token → MCP-Handshake; danach
   `claude mcp add` gegen die LAN-IP.

---

## 11. Feature: Client-seitiger Stdio↔HTTP-Proxy für Claude Code (`movieplexx connect`)

Stand: 2026-07-11 · Ziel: Registrierung des NAS-Servers bei **Claude Code** so
vereinfachen, dass der Nutzer nur noch `MCP_AUTH_TOKEN` als Parameter setzt,
statt den vollständigen `Authorization: Bearer <TOKEN>`-Header von Hand zu
tippen.

### 11.1 Ausgangslage

§10.5 registriert den NAS-Server bei Claude Code über den **nativen
HTTP-Transport**:

```bash
claude mcp add --transport http movieplexx http://192.168.1.50:8000/mcp \
  --header "Authorization: Bearer <TOKEN>"
```

Das funktioniert, verlangt aber, dass der Nutzer den kompletten Header-String
(inkl. `Bearer `-Präfix) selbst zusammensetzt und in der Kommandozeile trägt.
Ziel dieses Features: der Nutzer übergibt nur den rohen Token als
Umgebungsvariable; das Zusammensetzen des Bearer-Headers übernimmt ein neuer,
lokaler Wrapper.

**Scope-Entscheidung:** nur **Claude Code CLI**. Claude Desktop bleibt bei der
in §10.5 dokumentierten `mcp-remote`-Bridge unverändert.

### 11.2 Architektur

Ein neuer Subcommand `movieplexx connect <url>` läuft **lokal** beim Client
(stdio-Transport, von Claude Code wie gewohnt als Prozess gespawnt) und
verhält sich nach außen wie ein normaler stdio-MCP-Server. Intern verbindet er
sich als **MCP-Client** zum entfernten Streamable-HTTP-Server auf dem NAS und
reicht `list_tools`/`call_tool`-Aufrufe transparent durch:

```
Claude Code ──stdio──▶ movieplexx connect ──HTTP + Bearer──▶ NAS (mcp, §10)
                        (liest MCP_AUTH_TOKEN
                         aus der Umgebung)
```

Da `server.py` ausschließlich Tools exponiert (keine Resources/Prompts,
siehe §5), muss der Proxy nur `ListToolsRequest` und `CallToolRequest`
weiterleiten — kein generischer Protokoll-Proxy nötig. Das hält die
Implementierung klein (~70–100 Zeilen) und nutzt ausschließlich Bausteine,
die über die bestehende `mcp`-Abhängigkeit bereits vorhanden sind
(`mcp.client.streamable_http`, `mcp.client.session.ClientSession`,
`mcp.server.lowlevel.Server`, `mcp.server.stdio.stdio_server`) — keine neue
Dependency.

```python
# src/movieplexx/proxy.py (neu, Skizze)
import os
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

async def run_proxy(url: str) -> None:
    token = os.environ.get("MCP_AUTH_TOKEN")
    if not token:                                    # fail-closed, wie Server-Seite
        raise SystemExit("MCP_AUTH_TOKEN is required for `movieplexx connect`")
    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as remote:
            await remote.initialize()

            local = Server("movieplexx-proxy")

            @local.list_tools()
            async def _list_tools():
                return (await remote.list_tools()).tools

            @local.call_tool()
            async def _call_tool(name: str, arguments: dict):
                result = await remote.call_tool(name, arguments)
                return result.content

            async with stdio_server() as (in_stream, out_stream):
                await local.run(in_stream, out_stream, local.create_initialization_options())
```

### 11.3 CLI-Änderung

Neuer Subcommand in `cli.py`, analog zu `serve`:

```bash
movieplexx connect <url>          # z.B. http://192.168.1.50:8000/mcp
```

Konfiguration ausschließlich über die bestehende Variable `MCP_AUTH_TOKEN`
(kein neues Env-Var-Vokabular) — fail-closed wie in §10.2.

### 11.4 Client-Registrierung (vereinfacht)

```bash
claude mcp add movieplexx --env MCP_AUTH_TOKEN=<TOKEN> -- movieplexx connect http://192.168.1.50:8000/mcp
```

Kein `--transport http`, kein manuell zusammengesetzter `--header`-String mehr
— Claude Code startet `movieplexx connect` wie jeden anderen stdio-Server,
der Token wandert als einfacher Parameter (`--env`) statt als Teil eines
Header-Strings.

### 11.5 Sicherheits-Überlegungen

- Kein neuer Vertrauensbereich: der Token verlässt weiterhin nur den
  lokalen Client-Prozess und das LAN zum NAS, exakt wie in §10.6.
- Der Token liegt weiterhin **cleartext** in der lokalen Claude-Code-Config
  (`--env`) — das ist eine Ergonomie-, keine Security-Verbesserung gegenüber
  §10.5. Gleiches Risikoprofil wie der bisherige `--header`-Ansatz.
- `movieplexx connect` validiert nichts zusätzlich; die eigentliche
  Autorisierung bleibt Aufgabe der Server-seitigen `BearerAuth`-Middleware
  (§10.3).

### 11.6 Umsetzungs-Checkliste

1. `src/movieplexx/proxy.py` mit `run_proxy()` (Skizze siehe §11.2) anlegen.
2. `cli.py` um Subcommand `connect <url>` erweitern (ruft `run_proxy` per
   `asyncio.run`).
3. README: Claude-Code-Abschnitt in §10.5-Pendant durch die vereinfachte
   `claude mcp add ... --env MCP_AUTH_TOKEN=...`-Variante ersetzen; Claude
   Desktop-Abschnitt bleibt unverändert.
4. Smoke-Test: `movieplexx connect` lokal gegen den laufenden NAS-`mcp`-Service
   starten, `list_showtimes` über den Proxy aufrufen und mit direktem
   HTTP-Aufruf vergleichen.
