from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.settings import get_settings
from app.models.orders import Order, OrderItem, PrintJob
from app.workers.print_jobs import (
    NonRetryablePrintJobError,
    execute_print_job,
)


@pytest.mark.asyncio
async def test_execute_print_job_respects_retry_limit(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.workers.print_jobs.async_session_factory", session_factory)

    settings = get_settings()
    monkeypatch.setattr(settings, "print_retry_max", 2, raising=False)

    async with session_factory() as session:
        order = Order(
            order_id=2100,
            order_number="202510172100-NA0001",
            total_price=Decimal("10.00"),
            status="paid",
            order_type="pickup",
        )
        session.add(order)
        session.add(
            OrderItem(
                item_id=21001,
                order_id=order.order_id,
                product_id=None,
                product_name="限次打印饮品",
                quantity=1,
                unit_price=Decimal("10.00"),
            )
        )
        job = PrintJob(
            order_id=order.order_id,
            status="pending",
            try_count=settings.print_retry_max,
        )
        session.add(job)
        await session.flush()
        job_id = job.job_id
        await session.commit()

    with pytest.raises(NonRetryablePrintJobError):
        await execute_print_job(job_id, settings=settings)

    async with session_factory() as session:
        refreshed = await session.get(PrintJob, job_id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.next_try_at is None
        assert str(settings.print_retry_max) in (refreshed.last_error or "")
