from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.models.orders import Order
from app.services.reservations import ReservationService


@pytest.mark.asyncio
async def test_reservation_send_due_reminders(db_session) -> None:
    settings = get_settings()
    original_flag = settings.reservation_enabled
    try:
        settings.reservation_enabled = True
        scheduled_at = datetime.now(tz=UTC).replace(microsecond=0) + timedelta(
            minutes=settings.reservation_reminder_minutes + 5
        )
        order = Order(
            order_number="RESV-REMINDER",
            user_id=1,
            total_price=Decimal("0.00"),
            status="paid",
            order_type="pickup",
            payment_status="paid",
            source="user",
            is_scheduled=True,
            scheduled_at=scheduled_at,
        )
        db_session.add(order)
        await db_session.flush()

        service = ReservationService(db_session, settings)
        now = scheduled_at - timedelta(minutes=settings.reservation_reminder_minutes) + timedelta(minutes=1)

        order_ids = await service.send_due_reminders(now)
        assert order_ids == [order.order_id]
        assert order.reminder_sent_at == now
    finally:
        settings.reservation_enabled = original_flag


@pytest.mark.asyncio
async def test_reservation_activate_due_orders(db_session) -> None:
    settings = get_settings()
    original_flag = settings.reservation_enabled
    try:
        settings.reservation_enabled = True
        scheduled_at = datetime.now(tz=UTC).replace(microsecond=0) - timedelta(minutes=1)
        order = Order(
            order_number="RESV-ACTIVATE",
            user_id=2,
            total_price=Decimal("0.00"),
            status="paid",
            order_type="pickup",
            payment_status="paid",
            source="user",
            is_scheduled=True,
            scheduled_at=scheduled_at,
        )
        db_session.add(order)
        await db_session.flush()

        service = ReservationService(db_session, settings)
        now = datetime.now(tz=UTC).replace(microsecond=0)

        order_ids = await service.activate_due_orders(now)
        assert order_ids == [order.order_id]
        assert order.status == "in_production"
        assert order.updated_at == now
    finally:
        settings.reservation_enabled = original_flag
