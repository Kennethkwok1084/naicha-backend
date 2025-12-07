from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.settings import get_settings


def get_openid_or_ip(request: Request) -> str:
    """优先使用openid限流，降级到IP"""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_access_token

            token = auth_header[7:]
            payload = decode_access_token(token)
            if payload.openid:
                return f"openid:{payload.openid}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


settings = get_settings()
limiter = Limiter(
    key_func=get_openid_or_ip,
    default_limits=settings.rate_limit_default_limits or None,
    headers_enabled=True,
    enabled=settings.rate_limit_enabled and not settings.perf_disable_http_overheads,
)


def init_rate_limiter(app: FastAPI) -> None:
    """Attach SlowAPI limiter and exception handlers to the FastAPI app."""
    app.state.limiter = limiter
    if limiter.enabled:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
