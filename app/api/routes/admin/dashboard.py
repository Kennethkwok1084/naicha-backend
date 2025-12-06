"""Dashboard 看板接口"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from slowapi.util import get_remote_address

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.schemas import DashboardResponseSchema
from app.services.dashboard import DashboardService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


async def get_dashboard_service(
    session: AsyncSession = Depends(get_async_session),
) -> DashboardService:
    return DashboardService(session, get_settings())


@router.get(
    "/dashboard",
    response_model=DashboardResponseSchema,
    summary="商家看板",
)
@limiter.limit("30/minute", key_func=_admin_rate_limit_key)
async def get_admin_dashboard(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    range: str = Query(default="day", description="预设时间范围：day/week/month/year"),
    compare: bool = Query(default=False, description="是否对比上一周期"),
    start_date: str | None = Query(default=None, description="自定义开始日期（YYYY-MM-DD）"),
    end_date: str | None = Query(default=None, description="自定义结束日期（YYYY-MM-DD）"),
    top_n: int = Query(default=10, ge=1, le=50, description="Top商品数量"),
) -> DashboardResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.DASHBOARD_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for dashboard access.",
        )

    # 参数验证和转换
    start_date_obj: date | None = None
    end_date_obj: date | None = None
    
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be in YYYY-MM-DD format",
            )
    
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be in YYYY-MM-DD format",
            )
    
    if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before or equal to end_date",
        )
    
    # 如果提供了自定义日期，优先使用
    if start_date_obj and end_date_obj:
        # 转换 date 为 UTC-aware datetime
        from datetime import UTC, time
        start_datetime = datetime.combine(start_date_obj, time.min, tzinfo=UTC)
        end_datetime = datetime.combine(end_date_obj, time.max, tzinfo=UTC)
        range_key_param = None
    else:
        start_datetime = None
        end_datetime = None
        range_key_param = range
    
    try:
        payload = await dashboard_service.get_dashboard(
            range_key=range_key_param,
            compare=compare,
            start_date=start_datetime,
            end_date=end_datetime,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return DashboardResponseSchema.model_validate(payload)
