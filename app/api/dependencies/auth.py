from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenScope, decode_access_token
from app.db.session import get_async_session
from app.models.accounts import Admin, User
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_auth_service(session: AsyncSession = Depends(get_async_session)) -> AuthService:
    return AuthService(session)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> Admin:
    if credentials is None:
        raise _unauthorized("Authorization header missing.")

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized(str(exc)) from exc

    if payload.scope != TokenScope.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient scope for admin resource.",
        )

    try:
        admin_id = int(payload.sub)
    except ValueError as exc:
        raise _unauthorized("Invalid token subject.") from exc

    service = AuthService(session)
    admin = await service.get_admin_by_id(admin_id)
    if not admin:
        raise _unauthorized("Admin not found or inactive.")
    return admin


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    if credentials is None:
        raise _unauthorized("Authorization header missing.")

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized(str(exc)) from exc

    if payload.scope != TokenScope.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient scope for user resource.",
        )

    try:
        user_id = int(payload.sub)
    except ValueError as exc:
        raise _unauthorized("Invalid token subject.") from exc

    service = AuthService(session)
    user = await service.get_user_by_id(user_id)
    if not user:
        raise _unauthorized("User not found or inactive.")
    return user
