"""想要统计接口"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.schemas import WantStatsResponseSchema
from app.services.want import WantService

router = APIRouter()


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


async def get_want_service(
    session: AsyncSession = Depends(get_async_session),
) -> WantService:
    return WantService(session, get_settings())


@router.get(
    "/want/stats",
    response_model=WantStatsResponseSchema,
    summary="想要统计概览",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def get_want_stats(
    request: Request,
    response: Response,
    range: str = Query(default="7d"),
    limit: int = Query(default=20, ge=1, le=100),
    admin: Admin = Depends(get_current_admin),
    want_service: WantService = Depends(get_want_service),
) -> WantStatsResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.STATS_WANT_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for want statistics.",
        )

    try:
        payload = await want_service.get_stats(range_key=range, limit=limit)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return WantStatsResponseSchema(
        range=payload["range"],
        start=payload["start"],
        end=payload["end"],
        top_products=payload["top_products"],
        daily_series=payload["daily_series"],
    )
