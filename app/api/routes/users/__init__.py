from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_service, get_current_user_optional
from app.core.security import TokenScope
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.metrics.auth import USER_LOGIN_TOTAL
from app.schemas import (
    PhoneBindRequestSchema,
    PhoneBindResponseSchema,
    UserLoginRequestSchema,
    UserLoginResponseSchema,
    UserSummarySchema,
)
from app.services.auth import AuthService
from app.services.phone import PhoneBindError, PhoneService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


async def _resolve_open_id(code: str) -> str:
    open_id = code.strip()
    if not open_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authorization code.",
        )
    # TODO: 集成微信/支付宝等对接, 此处暂以 code 作为 open_id
    return open_id


@router.post("/login", response_model=UserLoginResponseSchema)
async def user_login(
    payload: UserLoginRequestSchema,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserLoginResponseSchema:
    try:
        open_id = await _resolve_open_id(payload.code)
        user = await auth_service.ensure_user(
            open_id=open_id,
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
        )

        token = auth_service.issue_access_token(subject=str(user.user_id), scope=TokenScope.USER)
        USER_LOGIN_TOTAL.labels(result="success").inc()
        return UserLoginResponseSchema(
            access_token=token,
            user=UserSummarySchema(
                user_id=user.user_id,
                nickname=user.nickname,
                avatar_url=user.avatar_url,
                loyalty_points=user.loyalty_points,
            ),
        )
    except HTTPException:
        USER_LOGIN_TOTAL.labels(result="failure").inc()
        raise


async def get_phone_service(
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> PhoneService:
    return PhoneService(session, settings)


@router.post(
    "/phone/bind",
    response_model=PhoneBindResponseSchema,
    summary="绑定手机号并返回明文号码",
)
async def bind_phone_number(
    payload: PhoneBindRequestSchema,
    phone_service: PhoneService = Depends(get_phone_service),
    current_user=Depends(get_current_user_optional),
) -> PhoneBindResponseSchema:
    try:
        phone_number = await phone_service.bind_phone(
            code=payload.code,
            user=current_user,
            guest_session_id=payload.guest_session_id,
        )
        return PhoneBindResponseSchema(
            phone_number=phone_number,
            from_guest_session=current_user is None,
        )
    except PhoneBindError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
