"""微信小程序认证路由"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.models.accounts import User
from app.schemas.wechat_auth import (
    BindPhoneRequest,
    BindPhoneResponse,
    WeChatLoginRequest,
    WeChatLoginResponse,
)
from app.services.wechat_auth_service import WeChatAuthService

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/users", tags=["wechat-auth"])


@router.post(
    "/login",
    response_model=WeChatLoginResponse,
    summary="微信小程序登录",
    description="使用微信一次性code登录,返回access_token和refresh_token",
)
@limiter.limit("10/minute")  # IP级别限流
async def wechat_login(
    request: Request,
    payload: WeChatLoginRequest,
    db: AsyncSession = Depends(get_async_session),
) -> WeChatLoginResponse:
    """
    微信小程序登录接口

    - 验证code有效性和防重放
    - 调用微信jscode2session获取openid
    - 创建或更新用户信息
    - 返回JWT token
    """
    settings = get_settings()
    auth_service = WeChatAuthService(db)

    try:
        result = await auth_service.login_with_code(
            code=payload.code,
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
        )

        return WeChatLoginResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            user_id=result["user_id"],
            is_new_user=result["is_new_user"],
            expires_in=settings.access_token_expire_minutes * 60,
        )
    except ValueError as exc:
        from slowapi.util import get_remote_address

        logger.warning("wechat.login.failed", error=str(exc), ip=get_remote_address(request))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        from slowapi.util import get_remote_address

        logger.error("wechat.login.error", error=str(exc), ip=get_remote_address(request))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败,请稍后重试",
        ) from exc


@router.post(
    "/phone/bind",
    response_model=BindPhoneResponse,
    summary="绑定微信手机号",
    description="使用微信getPhoneNumber返回的code绑定手机号",
)
@limiter.limit("5/minute")  # 更严格的限流
async def bind_phone(
    request: Request,
    payload: BindPhoneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BindPhoneResponse:
    """
    绑定手机号接口

    - 需要已登录用户或提供guest_session_id
    - 验证code有效性和防重放
    - 调用微信API获取手机号
    - 绑定到当前用户
    """
    auth_service = WeChatAuthService(db)

    try:
        result = await auth_service.bind_phone_number(
            code=payload.code,
            user_id=current_user.user_id,
            guest_session_id=payload.guest_session_id,
        )

        return BindPhoneResponse(
            phone=result["phone"],
            from_guest_session=result["from_guest_session"],
        )
    except ValueError as exc:
        from slowapi.util import get_remote_address

        logger.warning(
            "wechat.bind_phone.failed",
            user_id=current_user.user_id,
            error=str(exc),
            ip=get_remote_address(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        from slowapi.util import get_remote_address

        logger.error(
            "wechat.bind_phone.error",
            user_id=current_user.user_id,
            error=str(exc),
            ip=get_remote_address(request),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="绑定手机号失败,请稍后重试",
        ) from exc
