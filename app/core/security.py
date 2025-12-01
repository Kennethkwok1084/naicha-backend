from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt
from pydantic import BaseModel, ValidationError

from app.core.settings import get_settings


class TokenScope(StrEnum):
    ADMIN = "admin"
    USER = "user"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    sub: str
    scope: TokenScope
    exp: int
    jti: str | None = None  # JWT ID,用于黑名单
    openid: str | None = None  # 用户openid

    @property
    def expires_at(self) -> datetime:
        return datetime.fromtimestamp(self.exp, tz=UTC)


class InvalidTokenError(Exception):
    """Raised when access token decoding fails."""


def hash_password(plain_password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # 当存储的密码哈希格式异常时, 直接视为验证失败
        return False


def hash_code(code: str) -> str:
    """对微信code进行SHA256哈希,用于防重放"""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _build_payload(
    subject: str,
    scope: TokenScope,
    expires_at: datetime,
    openid: str | None = None,
    include_jti: bool = False,
) -> dict[str, Any]:
    payload = {
        "sub": subject,
        "scope": scope.value,
        "exp": int(expires_at.timestamp()),
    }
    if openid:
        payload["openid"] = openid
    if include_jti:
        payload["jti"] = secrets.token_urlsafe(32)
    return payload


def create_access_token(
    subject: str,
    scope: TokenScope,
    expires_delta: timedelta | None = None,
    openid: str | None = None,
    include_jti: bool = False,
) -> str:
    settings = get_settings()
    
    # 如果显式提供了expires_delta，优先使用它（用于测试过期token等场景）
    if expires_delta is not None:
        ttl = expires_delta
    elif scope == TokenScope.REFRESH:
        ttl = timedelta(days=settings.refresh_token_expire_days)
    elif scope == TokenScope.USER:
        ttl = timedelta(minutes=settings.access_token_expire_minutes)
    else:
        ttl = timedelta(minutes=settings.jwt_expire_minutes)
    
    expires_at = datetime.now(tz=UTC) + ttl
    payload = _build_payload(subject, scope, expires_at, openid, include_jti)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


async def is_token_blacklisted(jti: str | None, session) -> bool:
    """检查token是否在黑名单中"""
    if not jti:
        return False
    
    from sqlalchemy import select
    from app.models.accounts import TokenBlacklist
    from datetime import UTC, datetime
    
    stmt = select(TokenBlacklist).where(
        TokenBlacklist.token_jti == jti,
        TokenBlacklist.expires_at > datetime.now(UTC),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        raw_payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return TokenPayload(**raw_payload)
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Token expired") from exc
    except (jwt.PyJWTError, ValidationError, ValueError) as exc:
        raise InvalidTokenError("Token invalid") from exc
