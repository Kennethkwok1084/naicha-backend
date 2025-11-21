from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import UserAddress
from app.schemas.user import UserAddressCreateSchema, UserAddressUpdateSchema


class UserService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_addresses(self, user_id: int) -> list[UserAddress]:
        stmt = select(UserAddress).where(UserAddress.user_id == user_id).order_by(UserAddress.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def create_address(self, user_id: int, payload: UserAddressCreateSchema) -> UserAddress:
        if payload.is_default:
            await self._unset_default(user_id)

        address = UserAddress(
            user_id=user_id,
            contact_name=payload.contact_name,
            phone=payload.phone,
            address_line=payload.address_line,
            lat=payload.lat,
            lng=payload.lng,
            is_default=payload.is_default,
        )
        self._session.add(address)
        await self._session.flush()

        # 如果当前用户没有默认地址则将新建地址设为默认
        if not payload.is_default:
            has_default = await self._session.scalar(
                select(UserAddress.address_id).where(
                    UserAddress.user_id == user_id,
                    UserAddress.is_default.is_(True),
                )
            )
            if has_default is None:
                address.is_default = True
                await self._session.flush()

        await self._session.commit()
        await self._session.refresh(address)
        return address

    async def update_address(
        self, user_id: int, address_id: int, payload: UserAddressUpdateSchema
    ) -> UserAddress | None:
        stmt = select(UserAddress).where(
            UserAddress.address_id == address_id, UserAddress.user_id == user_id
        )
        result = await self._session.execute(stmt)
        address = result.scalar_one_or_none()
        if address is None:
            return None

        updates = payload.model_dump(exclude_unset=True)
        if updates.get("is_default"):
            await self._unset_default(user_id)

        for field, value in updates.items():
            setattr(address, field, value)

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(address)
        return address

    async def delete_address(self, user_id: int, address_id: int) -> bool:
        stmt = select(UserAddress).where(
            UserAddress.address_id == address_id, UserAddress.user_id == user_id
        )
        result = await self._session.execute(stmt)
        address = result.scalar_one_or_none()
        if address is None:
            return False

        was_default = bool(address.is_default)
        await self._session.delete(address)
        await self._session.flush()

        if was_default:
            fallback = await self._session.execute(
                select(UserAddress).where(UserAddress.user_id == user_id).order_by(UserAddress.created_at)
            )
            replacement = fallback.scalars().first()
            if replacement:
                replacement.is_default = True
                await self._session.flush()

        await self._session.commit()
        return True

    async def _unset_default(self, user_id: int) -> None:
        result = await self._session.execute(
            select(UserAddress).where(
                UserAddress.user_id == user_id,
                UserAddress.is_default.is_(True),
            )
        )
        for record in result.scalars().all():
            record.is_default = False
        await self._session.flush()
