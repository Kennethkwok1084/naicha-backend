"""POS 快速建单接口"""
from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.metrics.admin_orders import (
    ADMIN_ORDER_CREATE_LATENCY_MS,
    ADMIN_ORDER_CREATED_TOTAL,
)
from app.models.accounts import Admin
from app.models.orders import AuditLog, Order, PrintJob
from app.schemas import (
    AdminOrderCreateRequestSchema,
    AdminOrderResponseSchema,
    OrderCreateRequestSchema,
)
from app.services.auth import AuthService
from app.services.dashboard import DashboardService
from app.services.orders import (
    OrderConflictError,
    OrderService,
    OrderValidationError,
)
from app.services.pickup_code import ensure_pickup_code
from app.workers import enqueue_print_job
from app.ws.manager import merchant_notifier

router = APIRouter()
logger = get_logger(__name__)

_POS_IMMEDIATE_CHANNELS: set[str] = {"cash", "pos_card"}


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


@router.post(
    "/orders",
    response_model=AdminOrderResponseSchema,
    summary="POS 快速建单",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def create_pos_order(
    request: Request,
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> AdminOrderResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.ORDERS_POS_CREATE.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for POS order creation.",
        )

    try:
        raw_body = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body.",
        ) from exc

    try:
        payload = AdminOrderCreateRequestSchema.model_validate(raw_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    # Clerk 角色限制支付渠道
    if admin.role == "clerk" and payload.payment_channel not in _POS_IMMEDIATE_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clerk role can only use in-store payment channels.",
        )

    idempotency_key = (
        request.headers.get("X-Idempotency-Key") or request.headers.get("Idempotency-Key") or ""
    ).strip()
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Idempotency-Key header is required.",
        )

    if not payload.buyer_open_id and not payload.guest_session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="buyer_open_id or guest_session_id is required.",
        )

    auth_service = AuthService(session)
    buyer_user = None
    if payload.buyer_open_id:
        buyer_user = await auth_service.get_user_by_open_id(payload.buyer_open_id)
        if buyer_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer not found.",
            )

    order_payload = OrderCreateRequestSchema(
        items=payload.items,
        order_type=payload.order_type,
        notes=payload.notes,
        guest_session_id=payload.guest_session_id,
        shop_id=1,
        user_phone=payload.buyer_phone or "pos_order",
    )

    order_service = OrderService(session, settings)
    print_job_state: dict[str, object] = {"job_id": None, "created": False}
    payment_status_holder: dict[str, str] = {"status": "pending"}
    broadcast_holder: dict[str, dict] = {"payload": None}

    async def _post_create(order: Order, order_items) -> None:
        order.source = "pos"
        order.created_by_admin_id = admin.admin_id
        order.payment_channel = payload.payment_channel
        if payload.payment_channel in _POS_IMMEDIATE_CHANNELS:
            order.payment_status = "paid"
            order.status = "paid"
            order.updated_at = datetime.now(tz=UTC)
            await ensure_pickup_code(order, session, settings)
        else:
            order.payment_status = "pending"
        payment_status_holder["status"] = order.payment_status

        await session.flush()

        if payload.print_job:
            job = PrintJob(order_id=order.order_id, status="pending")
            session.add(job)
            await session.flush()
            print_job_state["job_id"] = job.job_id
            print_job_state["created"] = True

        audit_log = AuditLog(
            actor_type="admin",
            actor_admin_id=admin.admin_id,
            action="pos.order.create",
            target_table="orders",
            target_id=str(order.order_id),
            before_json=None,
            after_json={
                "order_number": order.order_number,
                "total_price": float(order.total_price),
                "payment_channel": payload.payment_channel,
                "payment_status": order.payment_status,
            },
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
        session.add(audit_log)

        broadcast_holder["payload"] = {
            "type": "order.created",
            "order": {
                "order_id": order.order_id,
                "order_number": order.order_number,
                "status": order.status,
                "payment_status": order.payment_status,
                "payment_channel": payload.payment_channel,
                "total_price": float(order.total_price),
            },
        }

    start_time = time.perf_counter()
    metrics_result = "error"
    try:
        result = await order_service.create_order(
            payload=order_payload,
            idempotency_key=idempotency_key,
            user=buyer_user,
            post_create=_post_create,
        )
        metrics_result = "success"
    except OrderValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except OrderConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        try:
            ADMIN_ORDER_CREATE_LATENCY_MS.labels(payload.payment_channel).observe(elapsed_ms)
            ADMIN_ORDER_CREATED_TOTAL.labels(payload.payment_channel, metrics_result).inc()
        except Exception:
            logger.exception("admin.pos_order.metrics_failed", channel=payload.payment_channel)

    if broadcast_holder["payload"] is not None:
        try:
            await merchant_notifier.broadcast(broadcast_holder["payload"])
        except Exception:
            logger.exception(
                "admin.pos_order.broadcast_failed",
                order_number=result["order_number"],
            )

    job_id = print_job_state["job_id"]
    if job_id is None and payload.print_job:
        existing_job_id = await session.scalar(
            select(PrintJob.job_id).where(PrintJob.order_id == result["order_id"])
        )
        if existing_job_id is not None:
            job_id = existing_job_id
    if bool(print_job_state["created"]) and job_id is not None:
        try:
            enqueue_print_job(job_id)
        except Exception:
            logger.exception(
                "admin.pos_order.print_enqueue_failed",
                job_id=job_id,
                order_number=result["order_number"],
            )

    await DashboardService(session, settings).invalidate_cache()

    return AdminOrderResponseSchema(
        order_id=result["order_id"],
        order_number=result["order_number"],
        status=result["status"],
        payment_status=payment_status_holder["status"],
        payment_channel=payload.payment_channel,
        total_price=result["total_price"],
        created_at=result["created_at"],
        print_job_id=job_id,
    )
