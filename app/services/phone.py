from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.accounts import User
from app.models.orders import IdempotencyKey
from app.services.guest import GuestSessionService


class PhoneBindError(Exception):
    """手机号绑定流程中的业务异常。"""


class PhoneService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def bind_phone(
        self,
        *,
        code: str,
        user: User | None,
        guest_session_id: str | None,
    ) -> str:
        phone_number = await self._resolve_phone_number(code)
        await self._persist_binding(phone_number, user=user, guest_session_id=guest_session_id)
        return phone_number

    async def _resolve_phone_number(self, code: str) -> str:
        """
        调用微信换取手机号的占位实现。
        真实环境应改为调用微信 getPhoneNumber 接口并校验 appid/secret。
        """
        cleaned = code.strip()
        if not cleaned:
            raise PhoneBindError("code 不能为空。")

        digits = "".join(ch for ch in cleaned if ch.isdigit())
        if len(digits) >= 11:
            return digits[-11:]

        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        return f"1{digest[:10]}"

    async def _persist_binding(
        self,
        phone_number: str,
        *,
        user: User | None,
        guest_session_id: str | None,
    ) -> None:
        if user is None and not guest_session_id:
            raise PhoneBindError("需要登录或提供 guest_session_id。")

        if user is not None:
            prefs = dict(user.preferences_json or {})
            prefs["phone_number"] = phone_number
            user.preferences_json = prefs
            await self._session.flush()

        if guest_session_id:
            record = await self._session.get(IdempotencyKey, guest_session_id)
            if not record or record.scope != GuestSessionService.SCOPE:
                raise PhoneBindError("Guest session 不存在或类型不匹配。")
            if record.expire_at and record.expire_at < datetime.now(tz=UTC):
                raise PhoneBindError("Guest session has expired.")

            snapshot = dict(record.response_snapshot or {})
            snapshot["phone_number"] = phone_number
            record.response_snapshot = snapshot
            await self._session.flush()

        await self._session.commit()
