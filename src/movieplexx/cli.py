"""Command-line entrypoint: `scrape`, `scrape --loop`, `serve`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from time import perf_counter

from . import metrics
from . import scrape as scrape_mod
from . import store

log = logging.getLogger("movieplexx")


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def run_scrape_once() -> dict[str, int]:
    """One fetch + normalize + persist cycle, instrumented for Prometheus."""
    start = perf_counter()
    try:
        films, performances, stats = scrape_mod.scrape()
        conn = store.connect()
        try:
            store.init_db(conn)
            counts = store.save(conn, films, performances)
        finally:
            conn.close()
    except Exception:
        metrics.SCRAPE_FAILURE.inc()
        raise
    finally:
        metrics.SCRAPE_DURATION.observe(perf_counter() - start)

    metrics.SCRAPE_SUCCESS.inc()
    metrics.FILMS_SEEN.set(counts["films"])
    metrics.PERFORMANCES_SEEN.set(counts["performances"])
    if stats["parse_errors"]:
        metrics.PARSE_ERRORS.inc(stats["parse_errors"])
    log.info(
        "scrape ok: %d films, %d performances, %d parse errors",
        counts["films"], counts["performances"], stats["parse_errors"],
    )
    return counts


def cmd_scrape(args: argparse.Namespace) -> int:
    interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))
    if not args.loop:
        run_scrape_once()
        return 0
    metrics.start_metrics_server()
    log.info("starting scrape loop, interval=%ds", interval)
    while True:
        try:
            run_scrape_once()
        except Exception:  # noqa: BLE001 - keep the loop alive on transient errors
            log.exception("scrape failed; will retry next interval")
        time.sleep(interval)


def cmd_serve(_args: argparse.Namespace) -> int:
    from .server import mcp

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        log.info("serving MCP over stdio")
        mcp.run()  # local process, spawned by the client
        return 0
    if transport == "http":
        import uvicorn

        from .http import BearerAuth

        token = os.environ.get("MCP_AUTH_TOKEN")
        if not token:  # fail-closed: never expose the endpoint unauthenticated
            log.error("MCP_AUTH_TOKEN is required for MCP_TRANSPORT=http")
            return 1
        host = os.environ.get("MCP_HOST", "0.0.0.0")  # noqa: S104 - bound via host port mapping
        port = int(os.environ.get("MCP_PORT", "8000"))
        mcp.settings.streamable_http_path = os.environ.get("MCP_PATH", "/mcp")
        app = mcp.streamable_http_app()
        app.add_middleware(BearerAuth, token=token)
        log.info("serving MCP over http on %s:%d%s", host, port,
                 mcp.settings.streamable_http_path)
        uvicorn.run(app, host=host, port=port, log_level=os.environ.get(
            "LOG_LEVEL", "info").lower())
        return 0
    log.error("unknown MCP_TRANSPORT: %r", transport)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="movieplexx")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="Fetch the program and store it")
    p_scrape.add_argument("--loop", action="store_true",
                          help="Run forever, polling every POLL_INTERVAL_SECONDS")
    p_scrape.set_defaults(func=cmd_scrape)

    p_serve = sub.add_parser("serve", help="Run the MCP server (MCP_TRANSPORT=stdio|http)")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
