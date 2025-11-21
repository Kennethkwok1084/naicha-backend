from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_async_session
from app.metrics.shop import (
    DELIVERY_CHECK_TOTAL,
    SHOP_PROFILE_REQUEST_TOTAL,
    SHOP_STATUS_REQUEST_TOTAL,
)
from app.schemas import (
    DeliveryCheckRequestSchema,
    DeliveryCheckResponseSchema,
    ShopProfileSchema,
    ShopStatusSchema,
)
from app.services.shop import ShopProfileNotConfiguredError, ShopService

router = APIRouter(prefix="/api/v1/shop", tags=["shop"])


async def get_shop_service(
    session: AsyncSession = Depends(get_async_session),
) -> ShopService:
    return ShopService(session, get_settings())


@router.get("/status", response_model=ShopStatusSchema, summary="获取门店状态")
async def shop_status(service: ShopService = Depends(get_shop_service)) -> ShopStatusSchema:
    try:
        payload = await service.get_status_payload()
        SHOP_STATUS_REQUEST_TOTAL.labels(result="success").inc()
        return ShopStatusSchema(**payload)
    except Exception:
        SHOP_STATUS_REQUEST_TOTAL.labels(result="error").inc()
        raise


@router.get("/profile", response_model=ShopProfileSchema, summary="获取门店基础信息")
async def shop_profile(service: ShopService = Depends(get_shop_service)) -> ShopProfileSchema:
    try:
        payload = await service.get_profile_snapshot()
        SHOP_PROFILE_REQUEST_TOTAL.labels(result="success").inc()
        return ShopProfileSchema(**payload)
    except ShopProfileNotConfiguredError as exc:
        SHOP_PROFILE_REQUEST_TOTAL.labels(result="error").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        SHOP_PROFILE_REQUEST_TOTAL.labels(result="error").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shop profile snapshot 校验失败。",
        ) from exc


@router.post(
    "/delivery/check",
    response_model=DeliveryCheckResponseSchema,
    summary="检查地址是否在配送范围",
)
async def delivery_check(
    payload: DeliveryCheckRequestSchema,
    service: ShopService = Depends(get_shop_service),
) -> DeliveryCheckResponseSchema:
    try:
        deliverable, distance = await service.check_delivery(payload.lat, payload.lng)
    except ShopProfileNotConfiguredError as exc:
        DELIVERY_CHECK_TOTAL.labels(result="error").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    result = "deliverable" if deliverable else "out_of_range"
    DELIVERY_CHECK_TOTAL.labels(result=result).inc()
    
    return DeliveryCheckResponseSchema(
        deliverable=deliverable,
        distance_m=round(distance, 2),
    )
