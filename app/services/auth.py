from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenScope, create_access_token, verify_password
from app.models.accounts import Admin, User


class AuthService:
    """集中处理鉴权相关的数据访问与令牌生成。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def authenticate_admin(self, username: str, password: str) -> Admin | None:
        result = await self._session.execute(select(Admin).where(Admin.username == username))
        admin = result.scalar_one_or_none()
        if not admin:
            return None
        if not verify_password(password, admin.password_hash):
            return None
        return admin

    async def get_admin_by_id(self, admin_id: int) -> Admin | None:
        result = await self._session.execute(select(Admin).where(Admin.admin_id == admin_id))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_open_id(self, open_id: str) -> User | None:
        result = await self._session.execute(select(User).where(User.open_id == open_id))
        return result.scalar_one_or_none()

    async def ensure_user(
        self,
        *,
        open_id: str,
        nickname: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        user = await self.get_user_by_open_id(open_id)
        if user is None:
            user = User(open_id=open_id, nickname=nickname, avatar_url=avatar_url)
            bind = self._session.get_bind()
            if bind and bind.dialect.name == "sqlite":
                next_id = await self._session.scalar(
                    select(func.coalesce(func.max(User.user_id), 0) + 1)
                )
                if next_id is not None:
                    user.user_id = int(next_id)
            self._session.add(user)
            await self._session.flush()
            await self._session.refresh(user)
            return user

        updated = False
        if nickname is not None and nickname != user.nickname:
            user.nickname = nickname
            updated = True
        if avatar_url is not None and avatar_url != user.avatar_url:
            user.avatar_url = avatar_url
            updated = True

        if updated:
            await self._session.flush()
            await self._session.refresh(user)

        return user

    def issue_access_token(self, subject: str, scope: TokenScope) -> str:
        return create_access_token(subject=subject, scope=scope)
