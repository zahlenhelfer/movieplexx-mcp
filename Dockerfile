# syntax=docker/dockerfile:1.7

# ── Stage 1: Builder ────────────────────────────────────────
FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

# ── Stage 2: Runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DB_PATH=/data/movieplexx.db \
    TARGET_URL=https://movieplexx.de/programm/api/filtered-films \
    POLL_INTERVAL_SECONDS=3600 \
    USER_AGENT="MovieplexxProgrammMirror/0.1 (+kontakt@zahlenhelfer.de)" \
    METRICS_PORT=9000 \
    MCP_TRANSPORT=stdio \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    MCP_PATH=/mcp \
    LOG_LEVEL=INFO

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app \
 && mkdir -p /data && chown -R app:app /data
WORKDIR /app

COPY --from=builder /build/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
VOLUME ["/data"]
USER app

ENTRYPOINT ["python", "-m", "movieplexx.cli"]
CMD ["serve"]
