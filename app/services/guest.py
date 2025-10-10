from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.orders import IdempotencyKey


class GuestSessionService:
    SCOPE = "guest_session"

    def __init__(self, session: AsyncSession):
        self._session = session
        self._settings = get_settings()

    async def issue_session(self, existing_token: str | None = None) -> tuple[str, datetime]:
        if existing_token:
            record = await self._session.get(IdempotencyKey, existing_token)
            if record and record.scope == self.SCOPE and not self._is_expired(record.expire_at):
                new_expiry = self._calculate_expiry()
                record.expire_at = new_expiry
                await self._session.flush()
                await self._session.commit()
                return record.idempotency_key, new_expiry

        session_id = self._generate_token()
        expiry = self._calculate_expiry()
        new_record = IdempotencyKey(
            idempotency_key=session_id,
            scope=self.SCOPE,
            request_hash=None,
            response_snapshot=None,
            expire_at=expiry,
        )
        self._session.add(new_record)
        await self._session.flush()
        await self._session.commit()
        return session_id, expiry

    def _calculate_expiry(self) -> datetime:
        ttl_minutes = self._settings.guest_session_ttl_minutes
        ttl = max(ttl_minutes, 1)
        return datetime.now(tz=UTC) + timedelta(minutes=ttl)

    @staticmethod
    def _is_expired(expire_at: datetime | None) -> bool:
        if expire_at is None:
            return False
        return expire_at < datetime.now(tz=UTC)

    @staticmethod
    def _generate_token() -> str:
        return f"gs_{token_urlsafe(24)}"
