from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenScope, decode_access_token
from app.db.session import get_async_session
from app.models.orders import Order
from app.services.auth import AuthService
from app.ws.manager import merchant_notifier

router = APIRouter()

RECENT_MINUTES = 5


@router.websocket("/ws/merchant")
async def merchant_ws_gateway(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token invalid")
        return

    if payload.scope != TokenScope.ADMIN:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Insufficient scope")
        return

    try:
        admin_id = int(payload.sub)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid subject")
        return

    auth_service = AuthService(session)
    admin = await auth_service.get_admin_by_id(admin_id)
    if admin is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Admin not found")
        return

    await websocket.accept()
    await merchant_notifier.register(websocket)
    await websocket.send_json({"type": "connection.ready", "admin_id": admin.admin_id})
    await _send_recent_orders(session, websocket)

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                # 非 JSON 消息统一回 Pong
                await websocket.send_json({"type": "error", "message": "Invalid payload"})
                continue

            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.now(tz=UTC).isoformat()})
    finally:
        await merchant_notifier.unregister(websocket)


async def _send_recent_orders(session: AsyncSession, websocket: WebSocket) -> None:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=RECENT_MINUTES)
    stmt = (
        select(Order)
        .where(Order.status == "paid", Order.updated_at >= cutoff)
        .order_by(Order.updated_at.desc())
    )
    result = await session.execute(stmt)
    orders = result.scalars().all()
    if not orders:
        return

    await websocket.send_json(
        {
            "type": "order.paid.snapshot",
            "orders": [
                {
                    "order_id": order.order_id,
                    "order_number": order.order_number,
                    "total_price": float(order.total_price),
                    "status": order.status,
                    "paid_at": (order.updated_at or order.created_at).isoformat(),
                }
                for order in orders
            ],
        }
    )
