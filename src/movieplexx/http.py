"""Bearer-token auth and Streamable-HTTP transport wiring for the MCP server."""

from __future__ import annotations

import hmac
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("movieplexx.http")


class BearerAuth(BaseHTTPMiddleware):
    """Reject requests whose Authorization header is not `Bearer <token>`."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self._expected = f"Bearer {token}"

    async def dispatch(self, request: Request, call_next):
        header = request.headers.get("authorization", "")
        # constant-time compare avoids leaking the token via timing
        if not hmac.compare_digest(header, self._expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def run_http_server(
    mcp: FastMCP,
    *,
    host: str,
    port: int,
    path: str,
    token: str,
    allowed_hosts: list[str],
    tls_certfile: str | None = None,
    tls_keyfile: str | None = None,
    log_level: str = "info",
) -> None:
    """Serve `mcp` over Streamable-HTTP with bearer auth and DNS-rebinding protection.

    Set tls_certfile/tls_keyfile to terminate TLS directly in uvicorn instead of
    relying on an external reverse proxy - without it, the bearer token travels
    in cleartext on the wire.
    """
    import uvicorn

    # FastMCP() locked transport_security to 127.0.0.1/localhost at construction
    # time (its default host); extend allowed_hosts with the LAN address(es)
    # clients actually send as the Host header, so DNS-rebinding protection
    # stays enabled instead of rejecting every remote request.
    mcp.settings.streamable_http_path = path
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    )

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth, token=token)

    scheme = "https" if tls_certfile else "http"
    log.info("serving MCP over %s on %s:%d%s", scheme, host, port, path)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        ssl_certfile=tls_certfile,
        ssl_keyfile=tls_keyfile,
    )
