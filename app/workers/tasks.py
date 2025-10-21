from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from celery.utils.log import get_task_logger

from app.core.settings import Settings, get_settings
from app.db.session import async_session_factory
from app.metrics.tasks import (
    CELERY_TASK_RUNTIME_SECONDS,
    RECONCILIATION_DIFF_GAUGE,
    RECONCILIATION_RUN_TOTAL,
    RESERVATION_ACTIVATED_TOTAL,
    RESERVATION_REMINDER_TOTAL,
)
from app.services.reconciliation import ReconciliationService
from app.services.reservations import ReservationService
from app.workers.celery_app import celery_app
from app.workers.print_jobs import (
    RetryablePrintJobError,
    execute_print_job,
    recover_print_jobs,
)

logger = get_task_logger(__name__)
settings = get_settings()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_print_job",
    autoretry_for=(RetryablePrintJobError,),
    max_retries=settings.print_retry_max,
    retry_backoff=True,
    retry_backoff_max=300,
)
def process_print_job(self, job_id: int) -> None:
    started_at = time.perf_counter()
    try:
        asyncio.run(execute_print_job(job_id, settings=settings))
    except RetryablePrintJobError as exc:
        logger.warning("print_job.retry_requested", job_id=job_id, message=str(exc))
        raise
    except Exception as exc:
        logger.exception("print_job.unhandled_exception", job_id=job_id)
        raise exc
    finally:
        _observe_task_runtime("process_print_job", started_at)


async def trigger_print_job_recovery(
    limit: int = 50,
    *,
    now: datetime | None = None,
    custom_settings: Settings | None = None,
) -> list[int]:
    settings_override = custom_settings or settings
    job_ids = await recover_print_jobs(limit=limit, now=now, settings=settings_override)
    if not job_ids:
        return []

    from app.workers import enqueue_print_job

    for job_id in job_ids:
        enqueue_print_job(job_id)
    return job_ids


@celery_app.task(
    bind=False,
    name="app.workers.tasks.run_print_job_recovery",
)
def run_print_job_recovery(limit: int = 50) -> None:
    started_at = time.perf_counter()
    try:
        job_ids = asyncio.run(trigger_print_job_recovery(limit=limit))
        if job_ids:
            logger.info("print_job.recovery_enqueued", job_ids=job_ids)
    except Exception as exc:  # pragma: no cover
        logger.exception("print_job.recovery_failed", error=str(exc))
    finally:
        _observe_task_runtime("run_print_job_recovery", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.reservation_send_reminders",
)
def reservation_send_reminders() -> None:
    started_at = time.perf_counter()
    try:
        asyncio.run(_reservation_send_reminders())
    except Exception as exc:  # pragma: no cover
        logger.exception("reservation.reminder_failed", error=str(exc))
    finally:
        _observe_task_runtime("reservation_send_reminders", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.reservation_activate_due_orders",
)
def reservation_activate_due_orders() -> None:
    started_at = time.perf_counter()
    try:
        asyncio.run(_reservation_activate_due_orders())
    except Exception as exc:  # pragma: no cover
        logger.exception("reservation.activate_failed", error=str(exc))
    finally:
        _observe_task_runtime("reservation_activate_due_orders", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.run_daily_reconciliation",
)
def run_daily_reconciliation() -> None:
    started_at = time.perf_counter()
    try:
        asyncio.run(_run_daily_reconciliation())
    except Exception as exc:  # pragma: no cover
        logger.exception("reconciliation.task_failed", error=str(exc))
    finally:
        _observe_task_runtime("run_daily_reconciliation", started_at)


async def _reservation_send_reminders() -> None:
    if not settings.reservation_enabled:
        return

    now = datetime.now(tz=UTC)
    async with async_session_factory() as session:
        service = ReservationService(session, settings)
        async with session.begin():
            order_ids = await service.send_due_reminders(now)

    if order_ids:
        logger.info("reservation.reminder_sent", order_ids=order_ids)
        RESERVATION_REMINDER_TOTAL.inc(len(order_ids))


async def _reservation_activate_due_orders() -> None:
    if not settings.reservation_enabled:
        return

    now = datetime.now(tz=UTC)
    async with async_session_factory() as session:
        service = ReservationService(session, settings)
        async with session.begin():
            order_ids = await service.activate_due_orders(now)

    if order_ids:
        logger.info("reservation.activated_orders", order_ids=order_ids)
        RESERVATION_ACTIVATED_TOTAL.inc(len(order_ids))


async def _run_daily_reconciliation() -> None:
    async with async_session_factory() as session:
        service = ReconciliationService(session, settings)
        result = await service.run_daily()

    status_label = "diff" if result.total_differences else "clean"
    RECONCILIATION_RUN_TOTAL.labels(result=status_label).inc()
    RECONCILIATION_DIFF_GAUGE.labels(type="orders_without_payment").set(
        len(result.orders_without_payment)
    )
    RECONCILIATION_DIFF_GAUGE.labels(type="orders_without_refund").set(
        len(result.orders_without_refund)
    )
    RECONCILIATION_DIFF_GAUGE.labels(type="unmatched_payments").set(
        len(result.unmatched_payments)
    )


def _observe_task_runtime(task_name: str, started_at: float) -> None:
    duration = max(time.perf_counter() - started_at, 0.0)
    CELERY_TASK_RUNTIME_SECONDS.labels(task=task_name).observe(duration)
