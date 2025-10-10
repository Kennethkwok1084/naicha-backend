from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import UserAddress


class UserService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_addresses(self, user_id: int) -> list[UserAddress]:
        stmt = select(UserAddress).where(UserAddress.user_id == user_id).order_by(UserAddress.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars())
