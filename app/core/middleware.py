from uuid import uuid4

import structlog
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.settings import Settings

TRACE_HEADER = "X-Trace-Id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Inject trace identifiers into logs and responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or request.headers.get("trace-id")
        if not trace_id:
            trace_id = uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id, path=request.url.path)

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers[TRACE_HEADER] = trace_id
        return response


def init_middleware(app: FastAPI, settings: Settings) -> None:
    """Register core middleware (trace id, proxy headers, CORS)."""
    app.add_middleware(TraceIdMiddleware)

    if settings.waf_trust_proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

    allow_origins = settings.allowed_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
