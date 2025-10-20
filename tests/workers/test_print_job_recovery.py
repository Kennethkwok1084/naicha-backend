from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.models.orders import Order, OrderItem, PrintJob
from app.workers.print_jobs import recover_print_jobs
from app.workers.tasks import trigger_print_job_recovery
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.mark.asyncio
async def test_celery_down_compensation(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.workers.print_jobs.async_session_factory", session_factory)

    settings = get_settings()
    monkeypatch.setattr(settings, "print_recovery_interval_seconds", 5, raising=False)

    async with session_factory() as session:
        order = Order(
            order_id=1200,
            order_number="202510171200-NA0001",
            total_price=Decimal("22.00"),
            status="paid",
            order_type="pickup",
        )
        session.add(order)
        session.add(
            OrderItem(
                item_id=12001,
                order_id=order.order_id,
                product_id=None,
                product_name="打印饮品",
                quantity=1,
                unit_price=Decimal("22.00"),
            )
        )
        job = PrintJob(
            order_id=order.order_id,
            status="pending",
            next_try_at=datetime.now(tz=UTC) - timedelta(seconds=30),
        )
        session.add(job)
        await session.flush()
        job_id = job.job_id
        await session.commit()

    enqueue_calls: list[int] = []

    import app.workers as workers_module

    def record_enqueue(job_identifier: int) -> None:
        enqueue_calls.append(job_identifier)

    monkeypatch.setattr(workers_module, "enqueue_print_job", record_enqueue)

    recovered = await trigger_print_job_recovery(
        limit=10,
        now=datetime.now(tz=UTC),
        custom_settings=settings,
    )

    assert recovered == [job_id]
    assert enqueue_calls == [job_id]


@pytest.mark.asyncio
async def test_duplicate_scan_idempotent(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.workers.print_jobs.async_session_factory", session_factory)

    settings = get_settings()

    async with session_factory() as session:
        order = Order(
            order_id=1300,
            order_number="202510171300-NA0001",
            total_price=Decimal("15.00"),
            status="paid",
            order_type="pickup",
        )
        session.add(order)
        job = PrintJob(
            order_id=order.order_id,
            status="pending",
            next_try_at=datetime.now(tz=UTC) - timedelta(seconds=10),
        )
        session.add(job)
        await session.flush()
        job_id = job.job_id
        await session.commit()

    assert job_id is not None

    now = datetime.now(tz=UTC)

    async def run_scan():
        return await recover_print_jobs(limit=1, now=now, settings=settings)

    first, second = await asyncio.gather(run_scan(), run_scan())
    flattened = [*first, *second]

    assert flattened.count(job_id) <= 1
    if flattened:
        assert flattened == [job_id]
