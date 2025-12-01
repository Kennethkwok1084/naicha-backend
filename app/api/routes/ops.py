from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.dependencies.auth import get_current_admin
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.schemas import (
    OpsAutoCancelRequestSchema,
    OpsAutoCancelResponseSchema,
)
from app.services.orders import OrderService

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])
logger = get_logger(__name__)

_OPS_ALLOWED_ROLES = {"admin", "manager"}


@router.post(
    "/orders/auto-cancel",
    response_model=OpsAutoCancelResponseSchema,
    summary="手动触发待支付订单自动取消",
)
async def trigger_auto_cancel_orders(
    payload: OpsAutoCancelRequestSchema,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> OpsAutoCancelResponseSchema:
    if admin.role not in _OPS_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权执行自动取消任务。",
        )

    cutoff_minutes = payload.cutoff_minutes or settings.order_pending_timeout_minutes
    cutoff_minutes = max(min(cutoff_minutes, 1440), 1)
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=cutoff_minutes)
    limit = max(min(payload.limit, 500), 1)
    reason = (
        payload.reason or "auto_cancel.manual_trigger"
    ).strip() or "auto_cancel.manual_trigger"

    service = OrderService(session, settings)
    transaction_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with transaction_ctx:
        cancelled_ids = await service.cancel_stale_pending_orders(
            cutoff,
            limit=limit,
            reason=reason,
            source="http",
        )

    logger.info(
        "ops.auto_cancel.triggered",
        operator=admin.username,
        operator_id=admin.admin_id,
        cancelled=len(cancelled_ids),
        cutoff=cutoff.isoformat(),
    )
    return OpsAutoCancelResponseSchema(
        cancelled_order_ids=cancelled_ids,
        count=len(cancelled_ids),
        cutoff_iso=cutoff,
        source="http",
        operator_admin_id=admin.admin_id,
    )
