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


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """
    限制请求体大小,防止恶意大包攻击

    注意: 此中间件应放在中间件链前端,在日志/限流之前执行
    """

    def __init__(self, app, max_body_size: int = 32768):
        """
        Args:
            max_body_size: 最大请求体大小(字节),默认32KB
        """
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next) -> Response:
        # 只检查可能有请求体的方法
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    if size > self.max_body_size:
                        from starlette.responses import JSONResponse

                        logger.warning(
                            "request_body_too_large",
                            content_length=size,
                            max_allowed=self.max_body_size,
                            path=request.url.path,
                        )
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": f"请求体过大,最大支持{self.max_body_size // 1024}KB"
                            },
                        )
                except ValueError:
                    pass  # Content-Length格式错误,由后续处理

        return await call_next(request)


def init_middleware(app: FastAPI, settings: Settings) -> None:
    """Register core middleware (trace id, proxy headers, CORS)."""
    # 请求体大小限制应放在最前面,避免处理大包浪费资源
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=32768)  # 32KB
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
