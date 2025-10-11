from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.orders import Order, PaymentRecord, PrintJob


def _sign(body: bytes) -> str:
    settings = get_settings()
    return hmac.new(settings.secret_key.encode("utf-8"), body, "sha256").hexdigest()


@pytest.mark.asyncio
async def test_wechat_payment_notify_success(db_session) -> None:
    order = Order(
        order_id=1,
        order_number="202510170001-NA0001",
        total_price=Decimal("17.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()

    payload = {
        "event_id": "evt_123",
        "order_number": order.order_number,
        "transaction_id": "txn_123",
        "amount": 17.0,
        "currency": "CNY",
        "channel": "wechat_jsapi",
        "status": "SUCCESS",
        "paid_at": datetime.now(tz=UTC).isoformat(),
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = _sign(body)

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/payments/notify/wechat",
                content=body,
                headers={"X-Wechat-Signature": signature},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "SUCCESS"

            # 重放同一通知应幂等
            response_second = await client.post(
                "/api/v1/payments/notify/wechat",
                content=body,
                headers={"X-Wechat-Signature": signature},
            )
            assert response_second.status_code == 200
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    refreshed_order = await db_session.get(Order, order.order_id)
    assert refreshed_order is not None
    assert refreshed_order.status == "paid"

    payment_records = await db_session.execute(
        select(PaymentRecord).where(PaymentRecord.txn_id == "txn_123")
    )
    assert payment_records.scalars().first() is not None

    job = await db_session.execute(select(PrintJob).where(PrintJob.order_id == order.order_id))
    assert job.scalars().first() is not None


@pytest.mark.asyncio
async def test_wechat_payment_notify_invalid_signature(db_session) -> None:
    order = Order(
        order_id=2,
        order_number="202510170002-NA0001",
        total_price=Decimal("30.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()

    payload = {
        "event_id": "evt_invalid",
        "order_number": order.order_number,
        "transaction_id": "txn_invalid",
        "amount": 30.0,
        "currency": "CNY",
        "channel": "wechat_jsapi",
        "status": "SUCCESS",
        "paid_at": datetime.now(tz=UTC).isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/payments/notify/wechat",
                content=body,
                headers={"X-Wechat-Signature": "invalid"},
            )
            assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_async_session, None)
