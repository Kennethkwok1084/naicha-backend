from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from threading import Lock

import redis
from celery.utils.log import get_task_logger
from redis.exceptions import RedisError

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

_lock_client: redis.Redis | None = None
_lock_client_disabled = False
_lock_client_lock = Lock()


def _get_lock_client() -> redis.Redis | None:
    global _lock_client_disabled, _lock_client
    if _lock_client_disabled:
        return None
    client = _lock_client
    if client is not None:
        return client

    with _lock_client_lock:
        client = _lock_client
        if client is not None:
            return client
        try:
            client = redis.Redis.from_url(settings.celery_broker_url, decode_responses=False)
        except Exception as exc:  # pragma: no cover - 初始化失败仅记录一次
            logger.warning("celery.lock.client_init_failed", error=str(exc))
            _lock_client_disabled = True
            return None
        _lock_client = client
        return client


def _resolve_lock_ttl(interval_seconds: int) -> int:
    if interval_seconds <= 0:
        return 120
    ttl = interval_seconds * 2
    ttl = max(ttl, 120)
    ttl = min(ttl, 7200)
    return ttl


def _acquire_task_lock(name: str, interval_seconds: int) -> tuple[bool, redis.lock.Lock | None]:
    client = _get_lock_client()
    if client is None:
        return True, None

    ttl = _resolve_lock_ttl(interval_seconds)
    try:
        lock = client.lock(name, timeout=ttl, blocking=False)
    except RedisError:
        # Should not happen because lock() does not hit network, but guard anyway.
        logger.warning("celery.lock.create_failed", lock=name)
        return True, None

    try:
        acquired = lock.acquire(blocking=False)
    except RedisError as exc:
        logger.warning("celery.lock.acquire_failed", lock=name, error=str(exc))
        return True, None

    if not acquired:
        return False, None
    return True, lock


def _release_task_lock(lock: redis.lock.Lock | None, name: str) -> None:
    if lock is None:
        return
    try:
        if getattr(lock, "owned", None):
            # redis-py >= 4 提供 owned() 判断当前客户端是否持有锁
            owned = lock.owned()  # type: ignore[call-arg]
        else:  # pragma: no cover - 兼容旧版本 redis-py
            owned = True
        if owned:
            lock.release()
    except RedisError as exc:
        logger.warning("celery.lock.release_failed", lock=name, error=str(exc))


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
    lock_name = "celery:lock:print_job_recovery"
    should_run, lock = _acquire_task_lock(lock_name, settings.print_recovery_interval_seconds)
    if not should_run:
        logger.info("celery.task_skipped_due_to_lock", task="run_print_job_recovery")
        _observe_task_runtime("run_print_job_recovery", started_at)
        return
    try:
        job_ids = asyncio.run(trigger_print_job_recovery(limit=limit))
        if job_ids:
            logger.info("print_job.recovery_enqueued", job_ids=job_ids)
    except Exception as exc:  # pragma: no cover
        logger.exception("print_job.recovery_failed", error=str(exc))
    finally:
        _release_task_lock(lock, lock_name)
        _observe_task_runtime("run_print_job_recovery", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.reservation_send_reminders",
)
def reservation_send_reminders() -> None:
    started_at = time.perf_counter()
    lock_name = "celery:lock:reservation_send_reminders"
    should_run, lock = _acquire_task_lock(lock_name, 60)
    if not should_run:
        logger.info("celery.task_skipped_due_to_lock", task="reservation_send_reminders")
        _observe_task_runtime("reservation_send_reminders", started_at)
        return
    try:
        asyncio.run(_reservation_send_reminders())
    except Exception as exc:  # pragma: no cover
        logger.exception("reservation.reminder_failed", error=str(exc))
    finally:
        _release_task_lock(lock, lock_name)
        _observe_task_runtime("reservation_send_reminders", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.reservation_activate_due_orders",
)
def reservation_activate_due_orders() -> None:
    started_at = time.perf_counter()
    lock_name = "celery:lock:reservation_activate_due_orders"
    should_run, lock = _acquire_task_lock(lock_name, 60)
    if not should_run:
        logger.info("celery.task_skipped_due_to_lock", task="reservation_activate_due_orders")
        _observe_task_runtime("reservation_activate_due_orders", started_at)
        return
    try:
        asyncio.run(_reservation_activate_due_orders())
    except Exception as exc:  # pragma: no cover
        logger.exception("reservation.activate_failed", error=str(exc))
    finally:
        _release_task_lock(lock, lock_name)
        _observe_task_runtime("reservation_activate_due_orders", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.run_daily_reconciliation",
)
def run_daily_reconciliation() -> None:
    started_at = time.perf_counter()
    lock_name = "celery:lock:run_daily_reconciliation"
    should_run, lock = _acquire_task_lock(lock_name, 86400)
    if not should_run:
        logger.info("celery.task_skipped_due_to_lock", task="run_daily_reconciliation")
        _observe_task_runtime("run_daily_reconciliation", started_at)
        return
    try:
        asyncio.run(_run_daily_reconciliation())
    except Exception as exc:  # pragma: no cover
        logger.exception("reconciliation.task_failed", error=str(exc))
    finally:
        _release_task_lock(lock, lock_name)
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
