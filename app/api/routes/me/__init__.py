from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.models.accounts import User
from app.schemas import (
    CouponsResponseSchema,
    LoyaltyTransactionsResponseSchema,
    UserAddressSchema,
    UserProfileSchema,
)
from app.schemas.loyalty import CouponSchema, LoyaltyTransactionSchema
from app.services.loyalty import LoyaltyService
from app.services.user import UserService

router = APIRouter(prefix="/api/v1/me", tags=["me"])


async def get_user_service(session: AsyncSession = Depends(get_async_session)) -> UserService:
    return UserService(session)


async def get_loyalty_service(
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> LoyaltyService:
    return LoyaltyService(session, settings)


@router.get("/profile", response_model=UserProfileSchema, summary="获取当前用户资料")
async def get_profile(current_user: User = Depends(get_current_user)) -> UserProfileSchema:
    return UserProfileSchema(
        user_id=current_user.user_id,
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        loyalty_points=current_user.loyalty_points,
    )


@router.get("/addresses", response_model=list[UserAddressSchema], summary="获取地址簿")
async def list_addresses(
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> list[UserAddressSchema]:
    addresses = await service.list_addresses(current_user.user_id)
    return [
        UserAddressSchema(
            address_id=address.address_id,
            contact_name=address.contact_name,
            phone=address.phone,
            address_line=address.address_line,
            lat=address.lat,
            lng=address.lng,
            is_default=address.is_default,
            created_at=address.created_at,
            updated_at=address.updated_at,
        )
        for address in addresses
    ]


@router.get(
    "/loyalty/transactions",
    response_model=LoyaltyTransactionsResponseSchema,
    summary="获取积分明细",
)
async def get_loyalty_transactions(
    current_user: User = Depends(get_current_user),
    service: LoyaltyService = Depends(get_loyalty_service),
    limit: int = Query(default=10, ge=1, le=100, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> LoyaltyTransactionsResponseSchema:
    """获取当前用户的积分明细"""
    transactions, total_count = await service.get_transactions(
        current_user.user_id, limit=limit, offset=offset
    )

    return LoyaltyTransactionsResponseSchema(
        transactions=[
            LoyaltyTransactionSchema(
                id=t.id,
                user_id=t.user_id,
                order_id=t.order_id,
                delta_points=t.delta_points,
                reason=t.reason,
                created_at=t.created_at,
            )
            for t in transactions
        ],
        total_count=total_count,
        current_points=current_user.loyalty_points,
        limit=limit,
        offset=offset,
    )


@router.get("/coupons", response_model=CouponsResponseSchema, summary="获取优惠券列表")
async def get_coupons(
    current_user: User = Depends(get_current_user),
    service: LoyaltyService = Depends(get_loyalty_service),
    status: str | None = Query(default=None, regex="^(active|used|expired|void)$", description="筛选状态"),
) -> CouponsResponseSchema:
    """获取当前用户的优惠券列表"""
    coupons, stats = await service.get_coupons(current_user.user_id, status_filter=status)

    return CouponsResponseSchema(
        coupons=[
            CouponSchema(
                coupon_id=c.coupon_id,
                user_id=c.user_id,
                type=c.type,
                status=c.status,
                meta_json=c.meta_json,
                issued_at=c.issued_at,
                used_at=c.used_at,
                used_in_order_id=c.used_in_order_id,
                created_at=c.created_at,
            )
            for c in coupons
        ],
        stats=stats,
    )
