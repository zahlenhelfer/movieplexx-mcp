"""ASGI bearer-token auth for the Streamable-HTTP MCP transport."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


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
