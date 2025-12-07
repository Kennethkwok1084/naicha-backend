from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.metrics.advertisements import ADS_CLICK_TOTAL, ADS_CONFIG_REQUEST_TOTAL, ADS_EXPOSE_TOTAL
from app.schemas import AdConfigResponseSchema, AdTrackRequestSchema
from app.services.advertisement import AdvertisementService

router = APIRouter(prefix="/api/v1/ads", tags=["ads"])


async def get_ad_service(
    session: AsyncSession = Depends(get_async_session),
) -> AdvertisementService:
    return AdvertisementService(session)


@router.get(
    "/config",
    response_model=AdConfigResponseSchema,
    summary="获取广告配置",
)
async def fetch_ad_config(
    slots: str = Query(..., description="逗号分隔的广告位编码, 如 HOME_BANNER,HOME_CARD"),
    platform: str = Query(default="miniapp", max_length=20),
    version: int = Query(default=0, ge=0, alias="ver"),
    service: AdvertisementService = Depends(get_ad_service),
) -> AdConfigResponseSchema:
    slot_list = [slot.strip() for slot in slots.split(",") if slot.strip()]
    payload = await service.get_config(slots=slot_list, platform=platform, current_version=version)

    # 记录请求结果
    if payload.version == version and not payload.slots:
        ADS_CONFIG_REQUEST_TOTAL.labels(result="version_match").inc()
    else:
        ADS_CONFIG_REQUEST_TOTAL.labels(result="success").inc()

    return payload


@router.post(
    "/track/expose",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="记录曝光事件",
)
async def track_expose(
    body: AdTrackRequestSchema = Body(...),
    service: AdvertisementService = Depends(get_ad_service),
) -> None:
    await service.track_expose(
        slot_code=body.slot_code,
        creative_id=body.creative_id,
        user_id=body.user_id,
        session_id=body.session_id,
    )
    ADS_EXPOSE_TOTAL.labels(slot=body.slot_code).inc()


@router.post(
    "/track/click",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="记录点击事件",
)
async def track_click(
    body: AdTrackRequestSchema = Body(...),
    service: AdvertisementService = Depends(get_ad_service),
) -> None:
    await service.track_click(
        slot_code=body.slot_code,
        creative_id=body.creative_id,
        user_id=body.user_id,
        session_id=body.session_id,
    )
    ADS_CLICK_TOTAL.labels(slot=body.slot_code).inc()
