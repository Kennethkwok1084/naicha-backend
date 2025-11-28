from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.catalog import Category, Product
from app.models.orders import IdempotencyKey, Order, PaymentRecord, PrintJob
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


def _sign(body: bytes) -> str:
    settings = get_settings()
    return hmac.new(settings.secret_key.encode("utf-8"), body, "sha256").hexdigest()


@pytest.mark.asyncio
async def test_payment_notify_after_order_created_via_api(model_test_engine) -> None:
    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    async def override_session():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    guest_session_id = "guest-perf-900"
    category = Category(category_id=900, name="性能测试", sort_order=1)
    product = Product(
        product_id=900,
        category_id=category.category_id,
        name="压力测试奶茶",
        description="性能回归",
        base_price=Decimal("12.00"),
        status="active",
        inventory_status="in_stock",
        stock_quantity=50,
    )
    guest_session = IdempotencyKey(
        idempotency_key=guest_session_id,
        scope="guest_session",
        request_hash=None,
        expire_at=None,
    )

    async with session_factory() as session:
        session.add_all([category, product, guest_session])
        await session.commit()

    app.dependency_overrides[get_async_session] = override_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            order_resp = await client.post(
                "/api/v1/orders",
                headers={"Idempotency-Key": "perf-order-900"},
                json={
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [
                        {"product_id": product.product_id, "quantity": 1, "selected_specs": []}
                    ],
                    "guest_session_id": guest_session_id,
                },
            )
            assert order_resp.status_code == 201
            order_payload = order_resp.json()
            order_number = order_payload["order_number"]

            notify_payload = {
                "event_id": "evt_perf_900",
                "order_number": order_number,
                "transaction_id": "txn_perf_900",
                "amount": order_payload["total_price"],
                "currency": "CNY",
                "channel": "wechat_jsapi",
                "status": "SUCCESS",
                "paid_at": datetime.now(tz=UTC).isoformat(),
            }
            body = json.dumps(notify_payload, separators=(",", ":")).encode("utf-8")
            signature = _sign(body)

            notify_resp = await client.post(
                "/api/v1/payments/notify/wechat",
                content=body,
                headers={"X-Wechat-Signature": signature},
            )
            assert notify_resp.status_code == 200

        async with session_factory() as session:
            result = await session.execute(select(Order).where(Order.order_number == order_number))
            order = result.scalar_one()
            assert order.status == "paid"
    finally:
        app.dependency_overrides.pop(get_async_session, None)


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
async def test_wechat_payment_notify_legacy_path(db_session) -> None:
    order = Order(
        order_id=3,
        order_number="202510170003-NA0001",
        total_price=Decimal("45.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()

    payload = {
        "event_id": "evt_legacy",
        "order_number": order.order_number,
        "transaction_id": "txn_legacy",
        "amount": 45.0,
        "currency": "CNY",
        "channel": "wechat_native",
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
                "/payments/notify/wechat",
                content=body,
                headers={"X-Wechat-Signature": signature},
            )
            assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    refreshed_order = await db_session.get(Order, order.order_id)
    assert refreshed_order is not None
    assert refreshed_order.status == "paid"


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
