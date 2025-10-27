import time
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
logger = structlog.get_logger(__name__)


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


class PerformanceMiddleware(BaseHTTPMiddleware):
    """记录请求性能指标"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        
        # 记录慢请求(超过500ms)
        if duration_ms > 500:
            logger.warning(
                "slow_request",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                status_code=response.status_code,
            )
        
        # 在响应头中添加性能指标
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
        
        return response


def init_middleware(app: FastAPI, settings: Settings) -> None:
    """Register core middleware (trace id, proxy headers, CORS)."""
    app.add_middleware(PerformanceMiddleware)
    app.add_middleware(TraceIdMiddleware)

    if not settings.disable_http_overheads:
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
