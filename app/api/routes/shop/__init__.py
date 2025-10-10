from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_async_session
from app.schemas import (
    DeliveryCheckRequestSchema,
    DeliveryCheckResponseSchema,
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
    payload = await service.get_status_payload()
    return ShopStatusSchema(**payload)


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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return DeliveryCheckResponseSchema(
        deliverable=deliverable,
        distance_m=round(distance, 2),
    )
