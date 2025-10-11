from fastapi import APIRouter, Depends, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, get_settings
from app.db.session import get_async_session

router = APIRouter(prefix="", tags=["system"])


def get_app_settings() -> Settings:
    return get_settings()


@router.get("/healthz", summary="健康检查")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/healthz/live", summary="Liveness Probe")
async def liveness_probe() -> dict[str, str]:
    return {"status": "live"}


@router.get("/healthz/ready", summary="Readiness Probe")
async def readiness_probe(
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - 转化为统一错误
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready.",
        ) from exc
    return {"status": "ready"}


@router.get("/metrics", summary="Prometheus 指标")
async def metrics(settings: Settings = Depends(get_app_settings)) -> Response:
    if not settings.prometheus_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prometheus metrics endpoint is disabled.",
        )

    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
