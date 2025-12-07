"""订单管理接口"""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from slowapi.util import get_remote_address
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from structlog import get_logger

from app.api.dependencies.auth import get_current_admin
from app.core.permissions import Permission, has_permission
from app.core.rate_limiter import limiter
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.models.accounts import Admin, User
from app.models.orders import Order, OrderItem
from app.schemas import (
    AdminOrderDetailSchema,
    AdminOrderItemSchema,
    AdminOrderListItemSchema,
    AdminOrderListResponseSchema,
    AdminOrderRefundRequestSchema,
    AdminOrderRefundResponseSchema,
    AdminOrderStatusUpdateRequestSchema,
    AdminPickupCodeUpdateRequestSchema,
    AdminPickupCodeUpdateResponseSchema,
    OrderAddressSchema,
)
from app.services.pickup_code import ensure_pickup_code
from app.utils.audit import record_audit_log

router = APIRouter()
logger = get_logger(__name__)


def _admin_rate_limit_key(request: Request) -> str:
    token = request.headers.get("Authorization")
    if token:
        return token
    return get_remote_address(request)


@router.get(
    "/orders",
    response_model=AdminOrderListResponseSchema,
    summary="订单列表",
)
@limiter.limit("30/minute", key_func=_admin_rate_limit_key)
async def list_orders(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="订单状态（逗号分隔）"),
    payment_status: str | None = Query(default=None, description="支付状态（逗号分隔）"),
    order_type: str | None = Query(default=None),
    payment_channel: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    user_phone: str | None = Query(default=None),
    order_number: str | None = Query(default=None),
    pickup_code: str | None = Query(default=None),
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
) -> AdminOrderListResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.ORDERS_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for order access.",
        )

    # 构建查询条件
    conditions = []

    if status:
        status_list = [s.strip() for s in status.split(",") if s.strip()]
        if status_list:
            conditions.append(Order.status.in_(status_list))

    if payment_status:
        payment_status_list = [s.strip() for s in payment_status.split(",") if s.strip()]
        if payment_status_list:
            conditions.append(Order.payment_status.in_(payment_status_list))

    if order_type:
        conditions.append(Order.order_type == order_type)

    if payment_channel:
        conditions.append(Order.payment_channel == payment_channel)

    if start_time:
        conditions.append(Order.created_at >= start_time)

    if end_time:
        conditions.append(Order.created_at <= end_time)

    if user_phone:
        conditions.append(Order.user_phone.ilike(f"%{user_phone}%"))

    if order_number:
        conditions.append(Order.order_number.ilike(f"%{order_number}%"))

    if pickup_code:
        conditions.append(Order.pickup_code.ilike(f"%{pickup_code}%"))

    # 查询总数
    count_stmt = select(func.count()).select_from(Order)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = await session.scalar(count_stmt) or 0

    # 查询数据
    stmt = (
        select(Order)
        .where(and_(*conditions) if conditions else True)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(stmt)
    orders = result.scalars().all()

    items = [
        AdminOrderListItemSchema(
            order_id=order.order_id,
            order_number=order.order_number,
            status=order.status,
            payment_status=order.payment_status,
            payment_channel=order.payment_channel,
            order_type=order.order_type,
            total_price=float(order.total_price),
            user_phone=order.user_phone,
            pickup_code=order.pickup_code,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )
        for order in orders
    ]

    return AdminOrderListResponseSchema(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 0,
    )


@router.get(
    "/orders/{order_id}",
    response_model=AdminOrderDetailSchema,
    summary="订单详情",
)
@limiter.limit("60/minute", key_func=_admin_rate_limit_key)
async def get_order_detail(
    request: Request,
    response: Response,
    order_id: int,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
) -> AdminOrderDetailSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.ORDERS_VIEW.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for order access.",
        )

    # 查询订单（包含订单项和用户信息）
    stmt = select(Order).options(selectinload(Order.items)).where(Order.order_id == order_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    # 获取用户信息
    user_nickname = None
    if order.user_id:
        user_stmt = select(User.nickname).where(User.user_id == order.user_id)
        user_nickname = await session.scalar(user_stmt)

    # 构建订单项列表
    items = [
        AdminOrderItemSchema(
            item_id=item.item_id,
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit_price=float(item.unit_price),
            selected_specs=item.selected_specs or [],
            subtotal=float(item.unit_price * item.quantity),
        )
        for item in order.items
    ]

    # 构建地址信息
    address = None
    if order.delivery_address:
        address = OrderAddressSchema(
            address=order.delivery_address.get("address"),
            detail=order.delivery_address.get("detail"),
            name=order.delivery_address.get("name"),
            phone=order.delivery_address.get("phone"),
            lat=order.delivery_address.get("lat"),
            lng=order.delivery_address.get("lng"),
        )

    # 构建时间线
    timeline = []
    if order.created_at:
        timeline.append({"status": "created", "time": order.created_at.isoformat()})
    if order.paid_at:
        timeline.append({"status": "paid", "time": order.paid_at.isoformat()})
    if order.completed_at:
        timeline.append({"status": "completed", "time": order.completed_at.isoformat()})
    if order.cancelled_at:
        timeline.append({"status": "cancelled", "time": order.cancelled_at.isoformat()})

    return AdminOrderDetailSchema(
        order_id=order.order_id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        payment_channel=order.payment_channel,
        order_type=order.order_type,
        source=order.source,
        total_price=float(order.total_price),
        coupon_discount=float(order.coupon_discount or 0),
        points_discount=float(order.points_discount or 0),
        final_amount=float(order.final_amount or order.total_price),
        user_id=order.user_id,
        user_phone=order.user_phone,
        user_nickname=user_nickname,
        pickup_code=order.pickup_code,
        notes=order.notes,
        created_at=order.created_at,
        updated_at=order.updated_at,
        paid_at=order.paid_at,
        completed_at=order.completed_at,
        cancelled_at=order.cancelled_at,
        created_by_admin_id=order.created_by_admin_id,
        items=items,
        address=address,
        timeline=timeline,
    )


@router.put(
    "/orders/{order_id}/status",
    summary="修改订单状态",
)
@limiter.limit("20/minute", key_func=_admin_rate_limit_key)
async def update_order_status(
    request: Request,
    response: Response,
    order_id: int,
    payload: AdminOrderStatusUpdateRequestSchema,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    # 权限检查
    if not has_permission(admin.role, Permission.ORDERS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for order modification.",
        )

    # 查询订单
    stmt = select(Order).where(Order.order_id == order_id).with_for_update()
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    # 记录状态变更前的信息
    old_status = order.status

    # 更新状态
    order.status = payload.status
    order.updated_at = datetime.now(tz=UTC)

    # 根据状态设置时间戳
    if payload.status == "completed":
        order.completed_at = datetime.now(tz=UTC)
    elif payload.status == "cancelled":
        order.cancelled_at = datetime.now(tz=UTC)

    # 记录审计日志
    await record_audit_log(
        session=session,
        admin=admin,
        action="order.status.update",
        target_table="orders",
        target_id=str(order_id),
        before_json={"status": old_status},
        after_json={"status": payload.status, "reason": payload.reason},
        request=request,
        reason=payload.reason,
    )

    await session.commit()

    logger.info(
        "order.status.updated",
        order_id=order_id,
        old_status=old_status,
        new_status=payload.status,
        admin_id=admin.admin_id,
    )

    return {
        "order_id": order_id,
        "status": order.status,
        "updated_at": order.updated_at,
    }


@router.post(
    "/orders/{order_id}/refund",
    response_model=AdminOrderRefundResponseSchema,
    summary="订单退款",
)
@limiter.limit("10/minute", key_func=_admin_rate_limit_key)
async def refund_order(
    request: Request,
    response: Response,
    order_id: int,
    payload: AdminOrderRefundRequestSchema,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
) -> AdminOrderRefundResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.ORDERS_REFUND.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for order refund.",
        )

    # 查询订单
    stmt = select(Order).where(Order.order_id == order_id).with_for_update()
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    # 验证订单状态
    if order.payment_status != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only paid orders can be refunded.",
        )

    if order.status in ("refunded", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order already refunded or cancelled.",
        )

    # 验证退款金额
    if payload.amount > float(order.final_amount or order.total_price):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount exceeds order total.",
        )

    # TODO: 实际对接支付渠道的退款接口
    # 这里仅做状态标记，实际退款需要调用微信支付等接口
    refund_id = f"RF{order.order_number}"

    # 更新订单状态
    order.status = "refunded"
    order.payment_status = "refunded"
    order.updated_at = datetime.now(tz=UTC)
    order.cancelled_at = datetime.now(tz=UTC)

    # 记录审计日志
    await record_audit_log(
        session=session,
        admin=admin,
        action="order.refund",
        target_table="orders",
        target_id=str(order_id),
        before_json={
            "status": "paid",
            "payment_status": "paid",
        },
        after_json={
            "status": "refunded",
            "refund_type": payload.refund_type,
            "amount": payload.amount,
            "reason": payload.reason,
        },
        request=request,
        reason=payload.reason,
    )

    await session.commit()

    logger.info(
        "order.refunded",
        order_id=order_id,
        refund_type=payload.refund_type,
        amount=payload.amount,
        admin_id=admin.admin_id,
    )

    return AdminOrderRefundResponseSchema(
        order_id=order_id,
        refund_type=payload.refund_type,
        amount=payload.amount,
        status="success" if payload.refund_type == "offline" else "processing",
        refund_id=refund_id if payload.refund_type == "offline" else None,
        message=(
            "线下退款已标记" if payload.refund_type == "offline" else "退款处理中，请稍后查询结果"
        ),
    )


@router.put(
    "/orders/{order_id}/pickup-code",
    response_model=AdminPickupCodeUpdateResponseSchema,
    summary="修改取餐码",
)
@limiter.limit("20/minute", key_func=_admin_rate_limit_key)
async def update_pickup_code(
    request: Request,
    response: Response,
    order_id: int,
    payload: AdminPickupCodeUpdateRequestSchema,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> AdminPickupCodeUpdateResponseSchema:
    # 权限检查
    if not has_permission(admin.role, Permission.ORDERS_EDIT.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for order modification.",
        )

    # 查询订单
    stmt = select(Order).where(Order.order_id == order_id).with_for_update()
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    # 验证订单状态
    if order.payment_status != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only paid orders can have pickup code modified.",
        )

    # 记录旧取餐码
    old_pickup_code = order.pickup_code

    # 如果提供了新取餐码，验证唯一性
    if payload.new_pickup_code:
        existing_stmt = select(Order.order_id).where(
            and_(
                Order.pickup_code == payload.new_pickup_code,
                Order.order_id != order_id,
            )
        )
        existing = await session.scalar(existing_stmt)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pickup code already exists for another order.",
            )
        order.pickup_code = payload.new_pickup_code
    else:
        # 自动生成新取餐码
        await ensure_pickup_code(order, session, settings)

    order.updated_at = datetime.now(tz=UTC)

    # 记录审计日志
    await record_audit_log(
        session=session,
        admin=admin,
        action="order.pickup_code.update",
        target_table="orders",
        target_id=str(order_id),
        before_json={"pickup_code": old_pickup_code},
        after_json={"pickup_code": order.pickup_code, "reason": payload.reason},
        request=request,
        reason=payload.reason,
    )

    await session.commit()

    logger.info(
        "order.pickup_code.updated",
        order_id=order_id,
        old_code=old_pickup_code,
        new_code=order.pickup_code,
        admin_id=admin.admin_id,
    )

    return AdminPickupCodeUpdateResponseSchema(
        order_id=order_id,
        old_pickup_code=old_pickup_code,
        new_pickup_code=order.pickup_code,
        updated_at=order.updated_at,
    )
