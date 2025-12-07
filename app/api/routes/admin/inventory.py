"""库存管理接口"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.schemas import (
    InventoryProductResponseSchema,
    InventorySpecOptionResponseSchema,
    InventoryUpdateRequestSchema,
)
from app.services.inventory import (
    InventoryNotFoundError,
    InventoryService,
)

router = APIRouter()


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


async def get_inventory_service(
    session: AsyncSession = Depends(get_async_session),
) -> InventoryService:
    return InventoryService(session, get_settings())


async def _load_json(request: Request) -> dict[str, object]:
    try:
        return await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc


def _parse_inventory_payload(request_body: dict[str, object]) -> InventoryUpdateRequestSchema:
    try:
        return InventoryUpdateRequestSchema.model_validate(request_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.put(
    "/inventory/products/{product_id}",
    response_model=InventoryProductResponseSchema,
    summary="更新商品库存状态",
)
@limiter.limit("20/minute", key_func=_admin_rate_limit_key)
async def update_product_inventory(
    request: Request,
    response: Response,
    product_id: int,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: InventoryService = Depends(get_inventory_service),
) -> InventoryProductResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.INVENTORY_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for inventory updates.",
        )

    raw = await _load_json(request)
    payload = _parse_inventory_payload(raw)

    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            # 服务层已包含审计日志记录（带正确的before_json）
            product = await service.update_product_inventory(
                product_id=product_id,
                inventory_status=payload.inventory_status,
                admin=admin,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
            )
        except InventoryNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return InventoryProductResponseSchema(
        product_id=product.product_id,
        inventory_status=product.inventory_status,
        updated_at=product.updated_at,
    )


@router.put(
    "/inventory/spec-options/{option_id}",
    response_model=InventorySpecOptionResponseSchema,
    summary="更新规格库存状态",
)
@limiter.limit("20/minute", key_func=_admin_rate_limit_key)
async def update_spec_option_inventory(
    request: Request,
    response: Response,
    option_id: int,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    service: InventoryService = Depends(get_inventory_service),
) -> InventorySpecOptionResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.INVENTORY_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for inventory updates.",
        )

    raw = await _load_json(request)
    payload = _parse_inventory_payload(raw)

    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        try:
            # 服务层已包含审计日志记录（带正确的before_json）
            option = await service.update_spec_option_inventory(
                option_id=option_id,
                inventory_status=payload.inventory_status,
                admin=admin,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
            )
        except InventoryNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return InventorySpecOptionResponseSchema(
        spec_option_id=option.option_id,
        inventory_status=option.inventory_status,
        updated_at=datetime.now(tz=UTC),
    )
