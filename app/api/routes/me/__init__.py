from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.db.session import get_async_session
from app.models.accounts import User
from app.schemas import UserAddressSchema, UserProfileSchema
from app.services.user import UserService

router = APIRouter(prefix="/api/v1/me", tags=["me"])


async def get_user_service(session: AsyncSession = Depends(get_async_session)) -> UserService:
    return UserService(session)


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
