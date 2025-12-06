"""支付匹配接口"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.schemas import (
    AdminPaymentMatchRequestSchema,
    AdminPaymentMatchResponseSchema,
)
from app.services.dashboard import DashboardService
from app.services.payment_match import (
    PaymentMatchAmbiguousError,
    PaymentMatchConflictError,
    PaymentMatchNotFoundError,
    PaymentMatchService,
)
from app.utils.audit import record_audit_log

router = APIRouter()
logger = get_logger(__name__)


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


@router.post(
    "/payments/match",
    response_model=AdminPaymentMatchResponseSchema,
    summary="静态码支付匹配",
)
@limiter.limit("20/minute", key_func=_admin_rate_limit_key)
async def match_static_payment(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> AdminPaymentMatchResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.PAYMENTS_MATCH.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for payment matching.",
        )

    try:
        raw_body = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc

    try:
        payload = AdminPaymentMatchRequestSchema.model_validate(raw_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    service = PaymentMatchService(session, settings)
    try:
        result = await service.match_payment(
            admin=admin,
            payload=payload,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
        
        # 记录审计日志
        await record_audit_log(
            session=session,
            admin=admin,
            action="payment.match",
            target_table="orders",
            target_id=str(result.order_id),
            before_json={"payment_status": "pending"},
            after_json={
                "payment_status": "paid",
                "amount": float(payload.amount),
                "match_method": "static_qr",
            },
            request=request,
        )
        
        await DashboardService(session, settings).invalidate_cache()
        return result
    except PaymentMatchAmbiguousError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Multiple matching orders found.",
                "result": "ambiguous",
                "candidates": [candidate.model_dump() for candidate in exc.candidates],
            },
        ) from exc
    except PaymentMatchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PaymentMatchConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
