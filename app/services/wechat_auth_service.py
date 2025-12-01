"""微信认证服务"""
from __future__ import annotations

import html
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_code, TokenScope
from app.models.accounts import User, WeChatUsedCode
from app.utils.wechat_client import WeChatAPIError, get_wechat_client

logger = structlog.get_logger()


class WeChatAuthService:
    """微信认证服务,处理登录、手机绑定等"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.wechat_client = get_wechat_client()

    async def login_with_code(
        self, code: str, nickname: str | None = None, avatar_url: str | None = None
    ) -> dict[str, str | int | bool]:
        """
        使用微信code登录
        返回: {"access_token": str, "refresh_token": str, "user_id": int, "is_new_user": bool}
        """
        # 1. 防重放检查（原子操作）
        code_hash = hash_code(code)

        # 2. 调用微信API
        try:
            session_info = await self.wechat_client.jscode2session(code)
        except WeChatAPIError as exc:
            logger.warning("wechat.login.api_error", errcode=exc.errcode, errmsg=exc.errmsg)
            raise ValueError("微信登录失败,请稍后重试") from exc

        openid = session_info["openid"]
        unionid = session_info.get("unionid")

        # 3. 原子标记code已使用（捕获并发冲突）
        try:
            await self._mark_code_used(code_hash, "login", openid)
        except Exception as exc:
            # 显式捕获数据库唯一约束冲突
            from sqlalchemy.exc import IntegrityError
            if isinstance(exc, IntegrityError) or isinstance(exc.__cause__, IntegrityError):
                await self.db.rollback()  # 清理失败事务状态
                logger.warning("wechat.login.code_reused_concurrent", code_hash=code_hash[:16])
                raise ValueError("登录凭证已使用,请重新获取") from exc
            # 其他异常向上抛
            raise

        # 4. 查找或创建用户
        user, is_new = await self._get_or_create_user(
            openid=openid,
            unionid=unionid,
            nickname=nickname,
            avatar_url=avatar_url,
        )

        # 5. 生成token
        access_token = create_access_token(
            subject=str(user.user_id),
            scope=TokenScope.USER,
            openid=openid,
            include_jti=True,
        )
        refresh_token = create_access_token(
            subject=str(user.user_id),
            scope=TokenScope.REFRESH,
            openid=openid,
            include_jti=True,
        )

        logger.info(
            "wechat.login.success",
            user_id=user.user_id,
            openid=openid,
            is_new_user=is_new,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user.user_id,
            "is_new_user": is_new,
        }

    async def bind_phone_number(
        self,
        code: str,
        user_id: int,
        guest_session_id: str | None = None,
    ) -> dict[str, str | bool]:
        """
        绑定手机号
        返回: {"phone": str, "from_guest_session": bool}
        """
        # 1. 防重放检查（原子操作）
        code_hash = hash_code(code)

        # 2. 验证用户
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        # 3. 调用微信API
        try:
            phone_info = await self.wechat_client.get_phone_number(code)
        except WeChatAPIError as exc:
            logger.warning(
                "wechat.bind_phone.api_error",
                user_id=user_id,
                errcode=exc.errcode,
                errmsg=exc.errmsg,
            )
            raise ValueError("获取手机号失败,请稍后重试") from exc

        pure_phone = phone_info["pure_phone_number"]

        # 4. 原子标记code已使用（捕获并发冲突）
        try:
            await self._mark_code_used(code_hash, "phone", user.open_id)
        except Exception as exc:
            # 显式捕获数据库唯一约束冲突
            from sqlalchemy.exc import IntegrityError
            if isinstance(exc, IntegrityError) or isinstance(exc.__cause__, IntegrityError):
                await self.db.rollback()  # 清理失败事务状态
                logger.warning("wechat.bind_phone.code_reused_concurrent", code_hash=code_hash[:16])
                raise ValueError("手机号凭证已使用,请重新获取") from exc
            # 其他异常向上抛
            raise

        # 5. 更新用户手机号
        user.phone = pure_phone
        await self.db.commit()

        logger.info(
            "wechat.bind_phone.success",
            user_id=user_id,
            phone_masked=self.wechat_client._mask_phone(pure_phone),
            from_guest=bool(guest_session_id),
        )

        return {
            "phone": self.wechat_client._mask_phone(pure_phone),
            "from_guest_session": bool(guest_session_id),
        }

    async def _mark_code_used(self, code_hash: str, code_type: str, openid: str) -> None:
        """标记code已使用"""
        used_code = WeChatUsedCode(
            code_hash=code_hash,
            code_type=code_type,
            used_by_openid=openid,
        )
        self.db.add(used_code)
        await self.db.commit()

    async def _get_or_create_user(
        self,
        openid: str,
        unionid: str | None,
        nickname: str | None,
        avatar_url: str | None,
    ) -> tuple[User, bool]:
        """
        获取或创建用户
        返回: (user, is_new_user)
        """
        # 查找现有用户
        stmt = select(User).where(User.open_id == openid)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # 更新昵称和头像(如果提供)
            if nickname:
                user.nickname = self._sanitize_nickname(nickname)
            if avatar_url:
                user.avatar_url = self._sanitize_avatar_url(avatar_url)
            if unionid and not user.union_id:
                user.union_id = unionid
            await self.db.commit()
            await self.db.refresh(user)
            return user, False

        # 创建新用户
        user = User(
            open_id=openid,
            union_id=unionid,
            nickname=self._sanitize_nickname(nickname) if nickname else None,
            avatar_url=self._sanitize_avatar_url(avatar_url) if avatar_url else None,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user, True

    @staticmethod
    def _sanitize_nickname(nickname: str | None) -> str | None:
        """昵称过滤和限长"""
        if not nickname:
            return None
        # HTML转义防止XSS
        sanitized = html.escape(nickname.strip())
        # 限长50字符
        return sanitized[:50] if len(sanitized) > 50 else sanitized

    @staticmethod
    def _sanitize_avatar_url(avatar_url: str | None) -> str | None:
        """头像URL过滤和限长"""
        if not avatar_url:
            return None
        # 简单验证URL格式
        if not avatar_url.startswith(("http://", "https://")):
            return None
        # 限长500字符
        return avatar_url[:500] if len(avatar_url) > 500 else avatar_url
