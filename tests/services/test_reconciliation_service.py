from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.core.settings import get_settings
from app.models.orders import Order, PaymentRecord
from app.services.reconciliation import ReconciliationService


async def _seed_order(
    db_session,
    *,
    status: str,
    payment_status: str,
    total: Decimal,
    created_at: datetime,
) -> Order:
    order = Order(
        order_number="RECON-001",
        total_price=total,
        status=status,
        payment_status=payment_status,
        order_type="pickup",
        source="user",
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(order)
    await db_session.flush()
    return order


@pytest.mark.asyncio
async def test_reconciliation_identifies_missing_payment(db_session) -> None:
    base_time = datetime(2025, 10, 21, 3, 0, tzinfo=UTC)
    local_time = datetime(2025, 10, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    order = await _seed_order(
        db_session,
        status="paid",
        payment_status="paid",
        total=Decimal("20.00"),
        created_at=local_time.astimezone(UTC),
    )

    settings = get_settings()
    service = ReconciliationService(db_session, settings)

    result = await service.run_daily(reference=base_time)
    assert any(item["order_id"] == order.order_id for item in result.orders_without_payment)


@pytest.mark.asyncio
async def test_reconciliation_detects_unmatched_payment(db_session) -> None:
    base_time = datetime(2025, 10, 21, 3, 0, tzinfo=UTC)
    local_time = datetime(2025, 10, 20, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    await _seed_order(
        db_session,
        status="paid",
        payment_status="paid",
        total=Decimal("15.00"),
        created_at=local_time.astimezone(UTC),
    )

    payment = PaymentRecord(
        record_type="payment",
        channel="wechat_jsapi",
        amount=Decimal("15.00"),
        paid_at=(local_time + timedelta(hours=1)).astimezone(UTC),
        match_status="unmatched",
    )
    db_session.add(payment)
    await db_session.flush()

    service = ReconciliationService(db_session, get_settings())
    result = await service.run_daily(reference=base_time)
    assert result.unmatched_payments
