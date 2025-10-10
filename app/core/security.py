from __future__ import annotations

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


class TokenPayload(BaseModel):
    sub: str
    scope: TokenScope
    exp: int

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


def _build_payload(subject: str, scope: TokenScope, expires_at: datetime) -> dict[str, Any]:
    return {
        "sub": subject,
        "scope": scope.value,
        "exp": int(expires_at.timestamp()),
    }


def create_access_token(
    subject: str,
    scope: TokenScope,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    ttl = expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    expires_at = datetime.now(tz=UTC) + ttl
    payload = _build_payload(subject, scope, expires_at)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        raw_payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return TokenPayload(**raw_payload)
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Token expired") from exc
    except (jwt.PyJWTError, ValidationError, ValueError) as exc:
        raise InvalidTokenError("Token invalid") from exc
