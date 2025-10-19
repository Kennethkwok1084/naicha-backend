from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import status
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.api.routes.ws import merchant_ws_gateway
from app.core.security import TokenScope, create_access_token
from app.models.accounts import Admin
from app.models.orders import Order
from app.ws.manager import merchant_notifier


class StubWebSocket:
    def __init__(self, token: str):
        self.query_params = {"token": token}
        self.accepted = False
        self.sent_messages: list[dict] = []
        self.application_state = WebSocketState.CONNECTED
        self.closed: tuple[int, str | None] | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data) -> None:
        self.sent_messages.append(data)

    async def receive_json(self):
        raise WebSocketDisconnect()

    async def close(self, code: int, reason: str | None = None) -> None:
        self.closed = (code, reason)
        self.application_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_merchant_ws_offline_snapshot(db_session) -> None:
    admin = Admin(admin_id=100, username="merchant", password_hash="hash", role="admin")
    db_session.add(admin)

    order = Order(
        order_id=500,
        order_number="202510170500-NA0001",
        total_price=Decimal("18.00"),
        status="paid",
        order_type="pickup",
    )
    order.updated_at = datetime.now(tz=UTC)
    db_session.add(order)
    await db_session.flush()

    token = create_access_token(subject=str(admin.admin_id), scope=TokenScope.ADMIN)
    websocket = StubWebSocket(token)

    await merchant_ws_gateway(websocket, session=db_session)

    assert websocket.accepted is True
    assert websocket.closed is None
    assert websocket.sent_messages[0]["type"] == "connection.ready"
    snapshot = next(msg for msg in websocket.sent_messages if msg["type"] == "order.paid.snapshot")
    assert snapshot["orders"][0]["order_id"] == order.order_id
    assert not merchant_notifier._connections  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_merchant_ws_missing_token_results_close(db_session) -> None:
    websocket = StubWebSocket(token="")
    websocket.query_params = {}

    await merchant_ws_gateway(websocket, session=db_session)

    assert websocket.accepted is False
    assert websocket.closed is not None
    assert websocket.closed[0] == status.WS_1008_POLICY_VIOLATION


@pytest.mark.asyncio
async def test_merchant_notifier_broadcasts_to_multiple_connections() -> None:
    await merchant_notifier.shutdown()
    message = {"type": "order.paid", "order": {"order_id": 1}}
    socket_a = StubWebSocket(token="a")
    socket_b = StubWebSocket(token="b")
    await merchant_notifier.register(socket_a)
    await merchant_notifier.register(socket_b)

    try:
        await merchant_notifier.broadcast(message)
        assert socket_a.sent_messages[0] == message
        assert socket_b.sent_messages[0] == message
    finally:
        await merchant_notifier.unregister(socket_a)
        await merchant_notifier.unregister(socket_b)
        assert not merchant_notifier._connections  # type: ignore[attr-defined]
    await merchant_notifier.shutdown()
