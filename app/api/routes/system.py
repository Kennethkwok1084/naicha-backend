from fastapi import APIRouter, Depends, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from app.core.settings import Settings, get_settings

router = APIRouter(prefix="", tags=["system"])


def get_app_settings() -> Settings:
    return get_settings()


@router.get("/healthz", summary="健康检查")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics", summary="Prometheus 指标")
async def metrics(settings: Settings = Depends(get_app_settings)) -> Response:
    if not settings.prometheus_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prometheus metrics endpoint is disabled.",
        )

    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
