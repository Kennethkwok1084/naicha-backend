from __future__ import annotations

import hmac
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.settings import get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.accounts import Coupon, LoyaltyTransaction, User
from app.models.orders import Order, OrderItem, PaymentRecord
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
        setup_session.add(
            OrderItem(
                item_id=2001,
                order_id=order.order_id,
                product_id=None,
                product_name="测试饮品",
                quantity=1,
                unit_price=Decimal("28.00"),
            )
        )
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


async def _prepare_order_for_loyalty(session, *, user_id: int, quantity: int, order_id: int) -> Order:
    order = Order(
        order_id=order_id,
        order_number=f"LOYALTY-{order_id}",
        total_price=Decimal("12.00"),
        status="pending_payment",
        order_type="pickup",
        user_id=user_id,
    )
    session.add(order)
    session.add(
        OrderItem(
            item_id=order_id * 10,
            order_id=order.order_id,
            product_id=None,
            product_name="积分饮品",
            quantity=quantity,
            unit_price=Decimal("6.00"),
        )
    )
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_payment_service_awards_loyalty_points(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        user = User(user_id=300, open_id="openid-loyalty")
        setup_session.add(user)
        await setup_session.flush()
        await _prepare_order_for_loyalty(setup_session, user_id=user.user_id, quantity=2, order_id=30)
        await setup_session.commit()

    async def noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(manager_module.merchant_notifier, "broadcast", noop_broadcast)

    payload = WechatPaymentNotifySchema(
        event_id="evt_loyalty",
        order_number="LOYALTY-30",
        transaction_id="txn_loyalty",
        amount=12.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        response = await service.handle_wechat_notification(
            payload,
            raw_body=raw_body,
            signature=_sign(raw_body),
        )

        assert response["status"] == "SUCCESS"

        user_refreshed = await session.get(User, 300)
        assert user_refreshed is not None
        assert user_refreshed.loyalty_points == 2

        award_tx = await session.scalar(
            select(LoyaltyTransaction).where(
                LoyaltyTransaction.user_id == 300,
                LoyaltyTransaction.order_id == 30,
                LoyaltyTransaction.reason == "order_paid",
            )
        )
        assert award_tx is not None

        coupon = await session.scalar(
            select(Coupon).where(Coupon.user_id == 300)
        )
        assert coupon is None


@pytest.mark.asyncio
async def test_payment_service_loyalty_issues_coupon_and_is_idempotent(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        user = User(user_id=400, open_id="openid-coupon", loyalty_points=9)
        setup_session.add(user)
        await setup_session.flush()
        await _prepare_order_for_loyalty(setup_session, user_id=user.user_id, quantity=2, order_id=40)
        await setup_session.commit()

    broadcasts: list[dict] = []

    async def capture_broadcast(message):
        broadcasts.append(message)

    monkeypatch.setattr(manager_module.merchant_notifier, "broadcast", capture_broadcast)

    payload = WechatPaymentNotifySchema(
        event_id="evt_coupon",
        order_number="LOYALTY-40",
        transaction_id="txn_coupon",
        amount=12.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        await service.handle_wechat_notification(payload, raw_body=raw_body, signature=_sign(raw_body))
        await service.handle_wechat_notification(payload, raw_body=raw_body, signature=_sign(raw_body))

        user_refreshed = await session.get(User, 400)
        assert user_refreshed is not None
        assert user_refreshed.loyalty_points == 1  # 9 + 2 - 10

        coupons = list(
            (await session.execute(select(Coupon).where(Coupon.user_id == 400))).scalars()
        )
        assert len(coupons) == 1
        assert coupons[0].type == "free_any_drink"

        order_paid_tx = list(
            (await session.execute(
                select(LoyaltyTransaction).where(
                    LoyaltyTransaction.user_id == 400,
                    LoyaltyTransaction.order_id == 40,
                    LoyaltyTransaction.reason == "order_paid",
                )
            )).scalars()
        )
        assert len(order_paid_tx) == 1

        coupon_tx = list(
            (await session.execute(
                select(LoyaltyTransaction).where(
                    LoyaltyTransaction.user_id == 400,
                    LoyaltyTransaction.reason == "coupon_grant",
                )
            )).scalars()
        )
        assert len(coupon_tx) == 1
