"""Prometheus metrics for the scraper.

Exposed on an HTTP endpoint (``/metrics``) when the scrape loop runs, so a
Prometheus server can scrape counts, durations and parse-error signals.
"""

from __future__ import annotations

import logging
import os

from prometheus_client import Counter, Gauge, Histogram, start_http_server

log = logging.getLogger("movieplexx.metrics")

SCRAPE_SUCCESS = Counter(
    "movieplexx_scrape_success_total", "Successful scrape cycles")
SCRAPE_FAILURE = Counter(
    "movieplexx_scrape_failure_total", "Failed scrape cycles (fetch or store error)")
SCRAPE_DURATION = Histogram(
    "movieplexx_scrape_duration_seconds", "Wall-clock duration of a scrape cycle")
FILMS_SEEN = Gauge(
    "movieplexx_films_seen", "Films returned by the last successful scrape")
PERFORMANCES_SEEN = Gauge(
    "movieplexx_performances_seen", "Performances stored by the last successful scrape")
PARSE_ERRORS = Counter(
    "movieplexx_parse_errors_total", "Films that failed to normalize (schema drift)")


def start_metrics_server(port: int | None = None) -> None:
    """Start the Prometheus HTTP endpoint. No-op if the port is 0."""
    port = int(os.environ.get("METRICS_PORT", "9000")) if port is None else port
    if port <= 0:
        log.info("metrics server disabled (METRICS_PORT<=0)")
        return
    start_http_server(port)
    log.info("metrics server listening on :%d/metrics", port)
