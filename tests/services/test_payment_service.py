from __future__ import annotations

import hmac
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.settings import get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.orders import Order, PaymentRecord
from app.schemas import WechatPaymentNotifySchema
from app.services.payments import (
    PaymentConflictError,
    PaymentService,
)
from app.ws import manager as manager_module


def _sign(body: bytes) -> str:
    settings = get_settings()
    return hmac.new(settings.secret_key.encode("utf-8"), body, "sha256").hexdigest()


@pytest.mark.asyncio
async def test_payment_service_amount_mismatch(db_session, monkeypatch) -> None:
    order = Order(
        order_id=10,
        order_number="202510170010-NA0001",
        total_price=Decimal("20.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()

    async def fake_broadcast(message):
        fake_broadcast.calls.append(message)

    fake_broadcast.calls = []
    monkeypatch.setattr(manager_module.merchant_notifier, "broadcast", fake_broadcast)

    service = PaymentService(db_session, get_settings())
    payload = WechatPaymentNotifySchema(
        event_id="evt_mismatch",
        order_number=order.order_number,
        transaction_id="txn_mismatch",
        amount=25.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )

    raw_body = payload.model_dump_json().encode("utf-8")

    with pytest.raises(PaymentConflictError):
        await service.handle_wechat_notification(payload, raw_body=raw_body, signature=_sign(raw_body))

    payment = await db_session.execute(
        select(PaymentRecord).where(PaymentRecord.txn_id == "txn_mismatch")
    )
    assert payment.scalars().first() is None
    assert fake_broadcast.calls == []


@pytest.mark.asyncio
async def test_payment_service_nested_transaction(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        order = Order(
            order_id=20,
            order_number="202510170020-NA0001",
            total_price=Decimal("28.00"),
            status="pending_payment",
            order_type="pickup",
        )
        setup_session.add(order)
        await setup_session.flush()
        order_id = order.order_id
        order_number = order.order_number
        await setup_session.commit()

    broadcasts: list[dict] = []

    async def fake_broadcast(message):
        broadcasts.append(message)

    monkeypatch.setattr(manager_module.merchant_notifier, "broadcast", fake_broadcast)

    payload = WechatPaymentNotifySchema(
        event_id="evt_nested",
        order_number=order_number,
        transaction_id="txn_nested",
        amount=28.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        async with session.begin():
            response = await service.handle_wechat_notification(
                payload,
                raw_body=raw_body,
                signature=_sign(raw_body),
            )

        assert response["status"] == "SUCCESS"

        refreshed = await session.get(Order, order_id)
        assert refreshed is not None
        assert refreshed.status == "paid"

        payment_record = await session.scalar(
            select(PaymentRecord).where(PaymentRecord.txn_id == "txn_nested")
        )
        assert payment_record is not None

    assert len(broadcasts) == 1
