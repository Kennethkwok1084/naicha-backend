"""广告管理接口"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.schemas import (
    AdCreativeCreateSchema,
    AdCreativeResponseSchema,
    AdCreativeUpdateSchema,
    AdPlacementCreateSchema,
    AdPlacementDetailSchema,
    AdPlacementOrderUpdateSchema,
    AdSlotCreateSchema,
    AdSlotSchema,
    AdSlotUpdateSchema,
)
from app.services.advertisement import (
    AdCreativeNotFoundError,
    AdPlacementConflictError,
    AdPlacementNotFoundError,
    AdSlotNotFoundError,
    AdvertisementService,
    AdvertisementServiceError,
)
from app.utils.audit import record_audit_log

router = APIRouter()


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


async def get_advertisement_service(
    session: AsyncSession = Depends(get_async_session),
) -> AdvertisementService:
    return AdvertisementService(session, get_settings())


async def _load_json(request: Request) -> dict[str, object]:
    try:
        return await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc


def _parse_payload(schema: type[BaseModel], request_body: dict[str, object]) -> BaseModel:
    try:
        return schema.model_validate(request_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


# Slot 广告位管理
@router.get(
    "/ads/slots",
    response_model=list[AdSlotSchema],
    summary="列出广告位",
)
@limiter.limit("30/minute", key_func=_admin_rate_limit_key)
async def list_ad_slots(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> list[AdSlotSchema]:
    if not has_permission(admin.role, Permission.ADS_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement access.",
        )

    slots = await service.list_slots()
    return [AdSlotSchema.model_validate(slot) for slot in slots]


@router.post(
    "/ads/slots",
    response_model=AdSlotSchema,
    status_code=status.HTTP_201_CREATED,
    summary="创建广告位",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def create_ad_slot(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> AdSlotSchema:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    raw = await _load_json(request)
    payload = _parse_payload(AdSlotCreateSchema, raw)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            slot = await service.create_slot(payload)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.slot.create",
                target_table="ad_slots",
                target_id=slot.slot_code,
                before_json=None,
                after_json={
                    "slot_code": slot.slot_code,
                    "name": slot.name,
                    "platform": slot.platform,
                },
                request=request,
            )
        except AdvertisementServiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
    return AdSlotSchema.model_validate(slot)


@router.put(
    "/ads/slots/{slot_code}",
    response_model=AdSlotSchema,
    summary="更新广告位",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def update_ad_slot(
    request: Request,
    response: Response,
    slot_code: str,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> AdSlotSchema:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    raw = await _load_json(request)
    payload = _parse_payload(AdSlotUpdateSchema, raw)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            slot = await service.update_slot(slot_code, payload)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.slot.update",
                target_table="ad_slots",
                target_id=slot_code,
                before_json={"slot_code": slot_code},
                after_json=payload.model_dump(exclude_unset=True),
                request=request,
            )
        except AdSlotNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AdSlotSchema.model_validate(slot)


# Creative 广告素材管理
@router.get(
    "/ads/creatives",
    response_model=list[AdCreativeResponseSchema],
    summary="列出广告素材",
)
@limiter.limit("30/minute", key_func=_admin_rate_limit_key)
async def list_ad_creatives(
    request: Request,
    response: Response,
    enabled: bool | None = Query(default=None),
    platform: str | None = Query(default=None),
    admin: Admin = Depends(get_current_admin),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> list[AdCreativeResponseSchema]:
    if not has_permission(admin.role, Permission.ADS_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement access.",
        )

    creatives = await service.list_creatives(enabled=enabled, platform=platform)
    return [AdCreativeResponseSchema.model_validate(item) for item in creatives]


@router.post(
    "/ads/creatives",
    response_model=AdCreativeResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="创建广告素材",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def create_ad_creative(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> AdCreativeResponseSchema:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    raw = await _load_json(request)
    payload = _parse_payload(AdCreativeCreateSchema, raw)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        creative = await service.create_creative(payload)

        # 记录审计日志
        await record_audit_log(
            session=session,
            admin=admin,
            action="ads.creative.create",
            target_table="ad_creatives",
            target_id=str(creative.creative_id),
            before_json=None,
            after_json={
                "creative_id": creative.creative_id,
                "title": creative.title,
                "enabled": creative.enabled,
            },
            request=request,
        )
    return AdCreativeResponseSchema.model_validate(creative)


@router.put(
    "/ads/creatives/{creative_id}",
    response_model=AdCreativeResponseSchema,
    summary="更新广告素材",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def update_ad_creative(
    request: Request,
    response: Response,
    creative_id: int,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> AdCreativeResponseSchema:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    raw = await _load_json(request)
    payload = _parse_payload(AdCreativeUpdateSchema, raw)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            creative = await service.update_creative(creative_id, payload)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.creative.update",
                target_table="ad_creatives",
                target_id=str(creative_id),
                before_json={"creative_id": creative_id},
                after_json=payload.model_dump(exclude_unset=True),
                request=request,
            )
        except AdCreativeNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AdCreativeResponseSchema.model_validate(creative)


@router.delete(
    "/ads/creatives/{creative_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除广告素材",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def delete_ad_creative(
    request: Request,
    response: Response,
    creative_id: int,
    reason: str = Query(..., min_length=1, description="删除原因（必填）"),
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> None:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            await service.delete_creative(creative_id)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.creative.delete",
                target_table="ad_creatives",
                target_id=str(creative_id),
                before_json={"creative_id": creative_id},
                after_json=None,
                request=request,
                reason=reason,
            )
        except AdCreativeNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# Placement 广告投放管理
@router.get(
    "/ads/placements",
    response_model=list[AdPlacementDetailSchema],
    summary="查看广告位投放列表",
)
@limiter.limit("30/minute", key_func=_admin_rate_limit_key)
async def list_ad_placements(
    request: Request,
    response: Response,
    slot_code: str = Query(..., description="广告位编码"),
    admin: Admin = Depends(get_current_admin),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> list[AdPlacementDetailSchema]:
    if not has_permission(admin.role, Permission.ADS_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement access.",
        )

    try:
        placements = await service.list_placements(slot_code)
    except AdSlotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [AdPlacementDetailSchema.model_validate(placement) for placement in placements]


@router.post(
    "/ads/placements",
    response_model=AdPlacementDetailSchema,
    status_code=status.HTTP_201_CREATED,
    summary="为广告位添加素材",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def create_ad_placement(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> AdPlacementDetailSchema:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    raw = await _load_json(request)
    payload = _parse_payload(AdPlacementCreateSchema, raw)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            placement = await service.add_placement(payload)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.placement.create",
                target_table="ad_placements",
                target_id=str(placement.placement_id),
                before_json=None,
                after_json={
                    "slot_code": payload.slot_code,
                    "creative_id": payload.creative_id,
                    "display_order": payload.display_order,
                },
                request=request,
            )
        except AdSlotNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except AdCreativeNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except AdPlacementConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        await session.refresh(placement, attribute_names=["creative"])
    return AdPlacementDetailSchema.model_validate(placement)


@router.put(
    "/ads/placements/order",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="批量更新投放排序",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def update_ad_placement_order(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> None:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    raw = await _load_json(request)
    payload = _parse_payload(AdPlacementOrderUpdateSchema, raw)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            await service.update_placement_order(payload)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.placement.reorder",
                target_table="ad_placements",
                target_id="batch",
                before_json=None,
                after_json={"updates": payload.model_dump()},
                request=request,
            )
        except AdPlacementNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/ads/placements/{placement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="移除广告投放",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def delete_ad_placement(
    request: Request,
    response: Response,
    placement_id: int,
    reason: str = Query(..., min_length=1, description="移除原因（必填）"),
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: AdvertisementService = Depends(get_advertisement_service),
) -> None:
    if not has_permission(admin.role, Permission.ADS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for advertisement management.",
        )

    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            await service.remove_placement(placement_id)

            # 记录审计日志
            await record_audit_log(
                session=session,
                admin=admin,
                action="ads.placement.delete",
                target_table="ad_placements",
                target_id=str(placement_id),
                before_json={"placement_id": placement_id},
                after_json=None,
                request=request,
                reason=reason,
            )
        except AdPlacementNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
