from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.settings import get_settings

settings = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
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
