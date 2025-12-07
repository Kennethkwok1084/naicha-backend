from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.accounts import User
from app.models.orders import Order, OrderItem, PaymentRecord, PrintJob


@pytest.mark.asyncio
async def test_order_defaults_and_related_entities(db_session) -> None:
    user = User(user_id=1, open_id="openid-order-1")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    order = Order(
        order_id=1,
        order_number="ORD-10001",
        user_id=user.user_id,
        total_price=Decimal("25.50"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    assert order.is_scheduled is False
    assert order.address_json is None

    item = OrderItem(
        item_id=1,
        order_id=order.order_id,
        product_name="测试饮品",
        quantity=2,
        unit_price=Decimal("12.75"),
    )
    db_session.add(item)
    await db_session.flush()

    invalid_item = OrderItem(
        item_id=2,
        order_id=order.order_id,
        product_name="非法商品",
        quantity=0,
        unit_price=Decimal("1.00"),
    )
    db_session.add(invalid_item)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_order_status_and_total_price_constraints(db_session) -> None:
    order = Order(
        order_id=10,
        order_number="ORD-INVALID-1",
        total_price=Decimal("10.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()

    order.status = "unknown"

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()

    order_negative = Order(
        order_id=11,
        order_number="ORD-INVALID-2",
        total_price=Decimal("-1.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order_negative)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_payment_record_defaults_and_constraints(db_session) -> None:
    payment = PaymentRecord(
        pay_id=1,
        record_type="payment",
        channel="wechat_jsapi",
        amount=Decimal("30.00"),
        paid_at=datetime.now(UTC),
    )
    db_session.add(payment)
    await db_session.flush()
    await db_session.refresh(payment)

    assert payment.currency == "CNY"
    assert payment.match_status == "unmatched"

    payment_invalid = PaymentRecord(
        pay_id=2,
        record_type="payment",
        channel="wechat_jsapi",
        amount=Decimal("-5.00"),
        paid_at=datetime.now(UTC),
    )
    db_session.add(payment_invalid)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_print_job_defaults(db_session) -> None:
    order = Order(
        order_id=20,
        order_number="ORD-PRINT-1",
        total_price=Decimal("15.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    job = PrintJob(job_id=1, order_id=order.order_id)
    db_session.add(job)
    await db_session.flush()
    await db_session.refresh(job)

    assert job.status == "pending"
    assert job.try_count == 0
