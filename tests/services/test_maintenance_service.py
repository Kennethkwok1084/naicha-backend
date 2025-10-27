from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.models.catalog import Product
from app.models.orders import Order, OrderItem
from app.services.maintenance import MaintenanceService


@pytest.mark.asyncio
async def test_enqueue_job_deduplicates(db_session) -> None:
    service = MaintenanceService(db_session, get_settings())
    job1 = await service.enqueue_job(job_type="cancel_stale_pending_orders")
    job2 = await service.enqueue_job(job_type="cancel_stale_pending_orders")

    assert job1.job_id == job2.job_id
    assert job1.status == "pending"


@pytest.mark.asyncio
async def test_execute_auto_cancel_job(db_session) -> None:
    settings = get_settings()
    product = Product(
        product_id=3301,
        name="维护奶茶",
        base_price=Decimal("12.00"),
        status="active",
        inventory_status="sold_out",
        stock_quantity=0,
    )
    created_at = datetime.now(tz=UTC) - timedelta(minutes=90)
    order = Order(
        order_id=88001,
        order_number="MT-001",
        total_price=Decimal("12.00"),
        status="pending_payment",
        order_type="pickup",
        payment_status="pending",
        source="user",
        created_at=created_at,
        updated_at=created_at,
    )
    item = OrderItem(
        item_id=91001,
        order_id=order.order_id,
        product_id=product.product_id,
        product_name=product.name,
        quantity=1,
        unit_price=Decimal("12.00"),
        selected_specs_json=None,
    )
    db_session.add_all([product, order, item])
    await db_session.flush()

    service = MaintenanceService(db_session, settings)
    job = await service.enqueue_job(
        job_type="cancel_stale_pending_orders",
        payload={"limit": 5, "cutoff_minutes": 30},
    )
    await db_session.flush()

    job_ids = await service.acquire_jobs(job_type="cancel_stale_pending_orders", limit=5)
    assert job.job_id in job_ids

    job_entity = await service.get_job(job.job_id)
    assert job_entity is not None

    result = await service.execute_job(job_entity)
    assert result["count"] == 1
    await service.complete_job(job_entity, result)

    await db_session.refresh(order)
    await db_session.refresh(product)
    assert order.status == "cancelled"
    assert product.stock_quantity == 1
