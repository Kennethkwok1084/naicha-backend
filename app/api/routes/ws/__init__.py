from __future__ import annotations

import asyncio
import structlog
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenScope, decode_access_token
from app.core.settings import Settings, get_settings
from app.db.session import get_async_session
from app.models.orders import Order
from app.services.auth import AuthService
from app.ws.manager import merchant_notifier

router = APIRouter()
logger = structlog.get_logger(__name__)

@router.websocket("/ws/merchant")
async def merchant_ws_gateway(
    websocket: WebSocket,
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

    # 使用独立session验证admin并发送初始消息，用完立即释放连接池
    async for session in get_async_session():
        auth_service = AuthService(session)
        admin = await auth_service.get_admin_by_id(admin_id)
        if admin is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Admin not found")
            return
        
        await websocket.accept()
        logger.info("websocket_accepted", admin_id=admin_id)
        await merchant_notifier.register(websocket)
        logger.info("notifier_registered", admin_id=admin_id)
        await websocket.send_json({"type": "connection.ready", "admin_id": admin.admin_id})
        logger.info("sent_connection_ready", admin_id=admin_id)
        app_state = getattr(getattr(websocket, "app", None), "state", None)
        settings = getattr(app_state, "settings", get_settings())
        await _send_recent_orders(session, websocket, settings)
        logger.info("sent_recent_orders", admin_id=admin_id)
        break  # 完成初始化后立即退出，释放session
    
    logger.info("entering_message_loop", admin_id=admin_id)
    # session已释放，开始心跳和消息循环
    last_pong = datetime.now(tz=UTC)
    ping_interval = 30
    pong_grace = 5

    async def heartbeat() -> None:
        nonlocal last_pong
        try:
            while True:
                await asyncio.sleep(ping_interval)
                elapsed = datetime.now(tz=UTC) - last_pong
                if elapsed.total_seconds() > ping_interval + pong_grace:
                    with suppress(Exception):
                        await websocket.close(
                            code=status.WS_1011_INTERNAL_ERROR,
                            reason="Heartbeat timeout",
                        )
                    break
                try:
                    await websocket.send_json({"type": "ping", "ts": datetime.now(tz=UTC).isoformat()})
                except WebSocketDisconnect:
                    break
                except Exception:
                    break
        except asyncio.CancelledError:
            raise

    ping_task = asyncio.create_task(heartbeat())

    try:
        while True:
            try:
                message = await websocket.receive_json()
                last_pong = datetime.now(tz=UTC)
            except WebSocketDisconnect:
                break
            except Exception:
                # 非 JSON 消息统一回 Pong
                await websocket.send_json({"type": "error", "message": "Invalid payload"})
                continue

            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.now(tz=UTC).isoformat()})
                last_pong = datetime.now(tz=UTC)
            elif message.get("type") == "pong":
                last_pong = datetime.now(tz=UTC)
    finally:
        ping_task.cancel()
        with suppress(asyncio.CancelledError):
            await ping_task
        await merchant_notifier.unregister(websocket)


async def _send_recent_orders(
    session: AsyncSession,
    websocket: WebSocket,
    settings: Settings,
) -> None:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=settings.merchant_ws_recent_minutes)
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
