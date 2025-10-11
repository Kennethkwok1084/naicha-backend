from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from app.api import api_router
from app.core.exceptions import init_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import init_middleware
from app.core.rate_limiter import init_rate_limiter
from app.core.settings import Settings, get_settings
from app.db.session import dispose_engine

settings: Settings = get_settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Naicha Backend",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.state.settings = settings

    init_middleware(app, settings)
    init_rate_limiter(app)
    init_exception_handlers(app)

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(api_router)

    return app


app = create_app()
