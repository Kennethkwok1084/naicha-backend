from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.settings import get_settings
from app.models.accounts import User
from app.models.catalog import Category, Product
from app.models.orders import Order
from app.models.shop import ShopProfile
from app.schemas import OrderCreateRequestSchema, OrderItemCreateSchema
from app.services.orders import OrderService
from app.services.reservations import ReservationService


@pytest.mark.asyncio
async def test_reservation_flow_end_to_end(db_session) -> None:
    settings = get_settings()
    original_flag = settings.reservation_enabled
    try:
        settings.reservation_enabled = True

        category = Category(category_id=6101, name="预约奶茶", sort_order=1)
        product = Product(
            product_id=6101,
            category_id=category.category_id,
            name="预约测试奶茶",
            description="",
            base_price=15,
            status="active",
            inventory_status="in_stock",
            stock_quantity=10,
        )
        db_session.add_all([category, product])

        profile = ShopProfile(
            id=1,
            timezone="Asia/Shanghai",
            open_hours_json=[
                {
                    "weekday": datetime.now(ZoneInfo("Asia/Shanghai")).isoweekday(),
                    "ranges": [["08:00", "22:00"]],
                }
            ],
        )
        db_session.add(profile)

        user = User(user_id=9001, open_id="reservation-e2e")
        db_session.add(user)
        await db_session.flush()

        order_service = OrderService(db_session, settings)
        scheduled_local = datetime.now(tz=ZoneInfo("Asia/Shanghai")) + timedelta(hours=2)
        create_payload = OrderCreateRequestSchema(
            items=[
                OrderItemCreateSchema(product_id=product.product_id, quantity=1, spec_option_ids=[])
            ],
            shop_id=1,
            order_type="pickup",
            scheduled_at=scheduled_local,
            notes="预约E2E",
            user_phone="13800000000",
        )

        created = await order_service.create_order(
            payload=create_payload,
            idempotency_key="reservation-e2e-001",
            user=user,
        )
        assert created["is_scheduled"] is True
        assert created["scheduled_at"] is not None
        assert created["status"] == "pending_payment"

        order = await db_session.get(Order, created["order_id"])
        assert order is not None
        order.status = "paid"
        order.payment_status = "paid"
        order.updated_at = datetime.now(tz=UTC)
        await db_session.flush()

        reservation_service = ReservationService(db_session, settings)
        queried_orders = await reservation_service._load_scheduled_orders()
        assert queried_orders, "expected scheduled order to be available"
        queried = queried_orders[0]
        assert queried.status == "paid"
        assert queried.payment_status == "paid"
        assert queried.reminder_sent_at is None
        scheduled_utc = queried.scheduled_at.astimezone(UTC)
        reminder_delta = timedelta(minutes=settings.reservation_reminder_minutes)
        reminder_call_time = scheduled_utc - reminder_delta + timedelta(seconds=1)
        reminder_ids = await reservation_service.send_due_reminders(reminder_call_time)
        assert order.order_id in reminder_ids
        assert order.reminder_sent_at == reminder_call_time

        activation_time = scheduled_local.astimezone(UTC) + timedelta(seconds=1)
        activated_ids = await reservation_service.activate_due_orders(activation_time)
        assert order.order_id in activated_ids
        assert order.status == "in_production"
    finally:
        settings.reservation_enabled = original_flag
