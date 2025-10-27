from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.settings import get_settings
from app.models.accounts import Coupon, LoyaltyTransaction, User
from app.models.orders import Order, OrderItem
from app.services.loyalty import LoyaltyService


@pytest.mark.asyncio
async def test_award_on_payment_accumulates_cups(db_session) -> None:
    settings = get_settings()

    user = User(user_id=1001, open_id="loyalty-user")
    order = Order(
        order_id=5001,
        order_number="CUP-5001",
        total_price=Decimal("36.00"),
        status="pending_payment",
        order_type="pickup",
        user_id=user.user_id,
    )
    items = [
        OrderItem(
            item_id=7001,
            order_id=order.order_id,
            product_id=None,
            product_name="奶茶A",
            quantity=2,
            unit_price=Decimal("12.00"),
        ),
        OrderItem(
            item_id=7002,
            order_id=order.order_id,
            product_id=None,
            product_name="奶茶B",
            quantity=1,
            unit_price=Decimal("12.00"),
        ),
    ]

    async with db_session.begin():
        db_session.add(user)
        db_session.add(order)
        db_session.add_all(items)

    loyalty_service = LoyaltyService(db_session, settings)
    async with db_session.begin():
        persisted_order = await db_session.get(Order, order.order_id)
        assert persisted_order is not None
        await loyalty_service.award_on_payment(persisted_order)

    stored_user = await db_session.get(User, user.user_id)
    assert stored_user is not None
    assert stored_user.loyalty_points == 3

    transactions = (
        await db_session.execute(
            select(LoyaltyTransaction).where(
                LoyaltyTransaction.user_id == user.user_id,
                LoyaltyTransaction.order_id == order.order_id,
            )
        )
    ).scalars().all()
    assert len(transactions) == 1
    assert transactions[0].delta_points == 3


@pytest.mark.asyncio
async def test_award_on_payment_triggers_coupon_when_threshold_reached(db_session) -> None:
    settings = get_settings()

    user = User(user_id=1002, open_id="coupon-user", loyalty_points=9)
    order = Order(
        order_id=5002,
        order_number="CUP-5002",
        total_price=Decimal("24.00"),
        status="pending_payment",
        order_type="pickup",
        user_id=user.user_id,
    )
    item = OrderItem(
        item_id=7003,
        order_id=order.order_id,
        product_id=None,
        product_name="奶茶C",
        quantity=2,
        unit_price=Decimal("12.00"),
    )

    async with db_session.begin():
        db_session.add(user)
        db_session.add(order)
        db_session.add(item)

    loyalty_service = LoyaltyService(db_session, settings)
    async with db_session.begin():
        persisted_order = await db_session.get(Order, order.order_id)
        assert persisted_order is not None
        await loyalty_service.award_on_payment(persisted_order)

    refreshed_user = await db_session.get(User, user.user_id)
    assert refreshed_user is not None
    assert refreshed_user.loyalty_points == 1

    coupons = (
        await db_session.execute(select(Coupon).where(Coupon.user_id == user.user_id))
    ).scalars().all()
    assert len(coupons) == 1
    assert coupons[0].type == "free_any_drink"

    transactions = (
        await db_session.execute(
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.user_id == user.user_id)
            .order_by(LoyaltyTransaction.id.asc())
        )
    ).scalars().all()
    assert len(transactions) == 2
    assert transactions[0].delta_points == 2
    assert transactions[1].delta_points == -10
