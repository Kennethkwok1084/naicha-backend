from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

import redis
from celery.utils.log import get_task_logger
from redis.exceptions import RedisError

from app.core.settings import Settings, get_settings
from app.db.session import async_session_factory
from app.metrics.payments import PAYMENT_SIDE_EFFECTS_TOTAL
from app.metrics.tasks import (
    CELERY_BEAT_LAST_HEARTBEAT_TIMESTAMP,
    CELERY_TASK_RUNTIME_SECONDS,
    RECONCILIATION_DIFF_GAUGE,
    RECONCILIATION_RUN_TOTAL,
    RESERVATION_ACTIVATED_TOTAL,
    RESERVATION_REMINDER_TOTAL,
)
from app.models.orders import Order
from app.services.loyalty import LoyaltyService
from app.services.maintenance import MaintenanceService
from app.services.orders import OrderService
from app.services.reconciliation import ReconciliationService
from app.services.reservations import ReservationService
from app.workers.celery_app import celery_app
from app.workers.print_jobs import (
    RetryablePrintJobError,
    execute_print_job,
    recover_print_jobs,
)
from app.ws.manager import merchant_notifier

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


def _acquire_task_lock(
    name: str, interval_seconds: int
) -> tuple[bool, redis.lock.Lock | None, bool]:
    client = _get_lock_client()
    if client is None:
        logger.warning("celery.lock.redis_unavailable", lock=name)
        return True, None, True

    ttl = _resolve_lock_ttl(interval_seconds)
    try:
        lock = client.lock(name, timeout=ttl, blocking=False)
    except RedisError:
        # Should not happen because lock() does not hit network, but guard anyway.
        logger.warning("celery.lock.create_failed", lock=name)
        return True, None, True

    try:
        acquired = lock.acquire(blocking=False)
    except RedisError as exc:
        logger.warning("celery.lock.acquire_failed", lock=name, error=str(exc))
        return True, None, True

    if not acquired:
        return False, None, False
    return True, lock, False


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
    should_run, lock, _ = _acquire_task_lock(lock_name, settings.print_recovery_interval_seconds)
    if not should_run:
        logger.info("celery.task_skipped_due_to_lock", extra={"task": "run_print_job_recovery"})
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
    name="app.workers.tasks.process_payment_side_effects",
)
def process_payment_side_effects(order_id: int, source: str = "payment_callback") -> None:
    started_at = time.perf_counter()
    try:
        asyncio.run(_process_payment_side_effects(order_id=order_id, source=source))
    except Exception as exc:  # pragma: no cover - 已记录日志
        PAYMENT_SIDE_EFFECTS_TOTAL.labels(result="failed", source=source).inc()
        logger.exception(
            "payment.side_effects_failed",
            order_id=order_id,
            source=source,
            error=str(exc),
        )
    else:
        PAYMENT_SIDE_EFFECTS_TOTAL.labels(result="success", source=source).inc()
    finally:
        _observe_task_runtime("process_payment_side_effects", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.reservation_send_reminders",
)
def reservation_send_reminders() -> None:
    started_at = time.perf_counter()
    lock_name = "celery:lock:reservation_send_reminders"
    should_run, lock, _ = _acquire_task_lock(lock_name, 60)
    if not should_run:
        logger.info(
            "celery.task_skipped_due_to_lock",
            extra={"task": "reservation_send_reminders"},
        )
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
    should_run, lock, _ = _acquire_task_lock(lock_name, 60)
    if not should_run:
        logger.info(
            "celery.task_skipped_due_to_lock",
            extra={"task": "reservation_activate_due_orders"},
        )
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
    name="app.workers.tasks.cancel_stale_pending_orders",
)
def cancel_stale_pending_orders(limit: int = 100) -> None:
    started_at = time.perf_counter()
    lock_name = "celery:lock:cancel_stale_pending_orders"
    interval = max(settings.order_pending_cleanup_interval_seconds, 30)
    should_run, lock, degraded = _acquire_task_lock(lock_name, interval)
    if not should_run:
        logger.info(
            "celery.task_skipped_due_to_lock",
            extra={"task": "cancel_stale_pending_orders"},
        )
        _observe_task_runtime("cancel_stale_pending_orders", started_at)
        return
    try:
        asyncio.run(_cancel_stale_pending_orders(limit=limit))
    except Exception as exc:  # pragma: no cover
        logger.exception("orders.cancel_stale_failed", error=str(exc))
        asyncio.run(_enqueue_auto_cancel_job(limit=limit))
    finally:
        _release_task_lock(lock, lock_name)
        _observe_task_runtime("cancel_stale_pending_orders", started_at)
    if degraded:
        asyncio.run(_enqueue_auto_cancel_job(limit=limit))


@celery_app.task(
    bind=False,
    name="app.workers.tasks.report_celery_beat",
)
def report_celery_beat() -> None:
    started_at = time.perf_counter()
    timestamp = datetime.now(tz=UTC)
    CELERY_BEAT_LAST_HEARTBEAT_TIMESTAMP.set(timestamp.timestamp())
    try:
        asyncio.run(_record_celery_beat(timestamp))
    except Exception as exc:  # pragma: no cover
        logger.exception("celery.beat_heartbeat_failed", error=str(exc))
    finally:
        _observe_task_runtime("report_celery_beat", started_at)


@celery_app.task(
    bind=False,
    name="app.workers.tasks.run_daily_reconciliation",
)
def run_daily_reconciliation() -> None:
    started_at = time.perf_counter()
    lock_name = "celery:lock:run_daily_reconciliation"
    should_run, lock, _ = _acquire_task_lock(lock_name, 86400)
    if not should_run:
        logger.info(
            "celery.task_skipped_due_to_lock",
            extra={"task": "run_daily_reconciliation"},
        )
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
    RECONCILIATION_DIFF_GAUGE.labels(type="unmatched_payments").set(len(result.unmatched_payments))


async def _cancel_stale_pending_orders(*, limit: int) -> None:
    cutoff = datetime.now(tz=UTC) - timedelta(
        minutes=max(settings.order_pending_timeout_minutes, 1)
    )
    async with async_session_factory() as session:
        service = OrderService(session, settings)
        async with session.begin():
            cancelled_ids = await service.cancel_stale_pending_orders(
                cutoff,
                limit=limit,
                reason="auto_cancel.pending_timeout",
                source="celery",
            )
    if cancelled_ids:
        logger.info(
            "orders.auto_cancelled",
            order_ids=cancelled_ids,
            reason="pending_timeout",
        )


async def _enqueue_auto_cancel_job(*, limit: int) -> None:
    async with async_session_factory() as session:
        service = MaintenanceService(session, settings)
        async with session.begin():
            await service.enqueue_job(
                job_type="cancel_stale_pending_orders",
                payload={
                    "limit": limit,
                    "cutoff_minutes": settings.order_pending_timeout_minutes,
                    "reason": "auto_cancel.db_cron",
                },
            )


def _observe_task_runtime(task_name: str, started_at: float) -> None:
    duration = max(time.perf_counter() - started_at, 0.0)
    CELERY_TASK_RUNTIME_SECONDS.labels(task=task_name).observe(duration)


async def _record_celery_beat(timestamp: datetime) -> None:
    async with async_session_factory() as session:
        service = MaintenanceService(session, settings)
        async with session.begin():
            await service.record_heartbeat("celery_beat", at=timestamp)


async def _process_payment_side_effects(order_id: int, *, source: str) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            order = await session.get(Order, order_id)
            if order is None:
                raise ValueError(f"Order {order_id} not found for side effects.")
            loyalty_service = LoyaltyService(session, settings)
            await loyalty_service.award_on_payment(order, skip_duplicate_check=True)
            broadcast_payload = _build_payment_broadcast_payload(order)

    if broadcast_payload:
        try:
            await merchant_notifier.broadcast(broadcast_payload)
        except Exception as exc:  # pragma: no cover - 广播失败仅记录
            logger.warning(
                "payment.side_effects_broadcast_failed",
                order_id=order_id,
                source=source,
                error=str(exc),
            )


def _build_payment_broadcast_payload(order: Order) -> dict[str, Any] | None:
    if order.order_id is None:
        return None
    paid_at = order.updated_at or datetime.now(tz=UTC)
    return {
        "type": "order.paid",
        "order": {
            "order_id": order.order_id,
            "order_number": order.order_number,
            "total_price": float(order.total_price or 0),
            "status": order.status,
            "paid_at": paid_at.isoformat(),
        },
    }


# ============================================================================
# 用户行为分析埋点任务
# ============================================================================


@celery_app.task(
    name="app.workers.tasks.batch_ingest_analytics_events",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,  # 任务级别可靠性配置：执行完才确认
    reject_on_worker_lost=True,  # Worker异常退出时拒绝任务
)
def batch_ingest_analytics_events(
    self,
    events_data: list[dict[str, Any]],
):
    """
    批量接收埋点事件并入库

    优化点:
    - API层打包整批事件投递,减少broker往返
    - Worker端拆分并批量插入,利用PostgreSQL批量性能
    - ON CONFLICT DO NOTHING 实现幂等
    - acks_late=True 确保任务失败自动重试

    Args:
        events_data: 事件列表,每个事件包含:
            - event_id: UUID字符串
            - user_id: 用户ID(可为None)
            - session_id: 会话标识
            - event_type: 事件类型
            - event_name: 事件名称
            - event_timestamp_ms: Unix毫秒时间戳
            - payload: 自定义属性字典
    """
    import asyncio

    from app.metrics.analytics import ANALYTICS_EVENTS_FAILED_TOTAL

    try:
        asyncio.run(_batch_insert_analytics_events_async(events_data))
    except Exception as exc:
        logger.error(
            "analytics.batch_insert_failed",
            error=str(exc),
            event_count=len(events_data),
            exc_info=True,
        )
        ANALYTICS_EVENTS_FAILED_TOTAL.inc()

        # 自动重试机制
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        # 重试耗尽,记录到死信(日志已记录,不再抛出)
        logger.critical(
            "analytics.batch_insert_exhausted",
            error=str(exc),
            event_count=len(events_data),
            retries=self.request.retries,
        )


async def _batch_insert_analytics_events_async(events_data: list[dict[str, Any]]):
    """
    异步批量插入埋点事件到数据库

    使用 ON CONFLICT DO NOTHING 实现幂等:
    - 重复的event_id会被自动跳过
    - 不影响批量插入的其他事件
    - 统计重复率用于监控客户端行为
    """
    from uuid import UUID

    from sqlalchemy.dialects.postgresql import insert

    from app.metrics.analytics import (
        ANALYTICS_BATCH_INSERT_DURATION_SECONDS,
        ANALYTICS_BATCH_SIZE,
        ANALYTICS_EVENTS_DUPLICATES_TOTAL,
        ANALYTICS_EVENTS_INSERTED_TOTAL,
    )
    from app.models.analytics import AnalyticsEvent

    if not events_data:
        return

    # 记录批量大小
    ANALYTICS_BATCH_SIZE.observe(len(events_data))

    # 转换为数据库模型数据
    db_events = []
    for event in events_data:
        db_events.append(
            {
                "event_id": UUID(event["event_id"]),
                "user_id": event.get("user_id"),
                "session_id": event.get("session_id"),
                "event_type": event["event_type"],
                "event_name": event["event_name"],
                "event_timestamp": datetime.fromtimestamp(
                    event["event_timestamp_ms"] / 1000, tz=UTC
                ),
                "payload": event.get("payload"),
            }
        )

    # 先统计各事件类型的数量（用于指标上报）
    event_type_counts: dict[str, int] = {}
    for event in events_data:
        event_type = event["event_type"]
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

    # 批量插入(带计时)
    start_time = time.time()
    async with async_session_factory() as session:
        try:
            stmt = insert(AnalyticsEvent).values(db_events)
            stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"])

            result = await session.execute(stmt)
            await session.commit()

            inserted = result.rowcount
            duplicates = len(db_events) - inserted

            # 按事件类型统计插入成功数
            # 注意: ON CONFLICT DO NOTHING 无法精确返回哪些行被插入
            # 当 duplicates=0 时所有事件都成功，可精确统计
            # 当 duplicates>0 时使用比例分配作为近似值
            if inserted > 0:
                if duplicates == 0:
                    # 所有事件都成功插入，可精确统计
                    for event_type, count in event_type_counts.items():
                        ANALYTICS_EVENTS_INSERTED_TOTAL.labels(event_type=event_type).inc(count)
                else:
                    # 存在重复，按比例分配（近似统计）
                    total_events = len(events_data)
                    for event_type, count in event_type_counts.items():
                        estimated_inserted = int(count * inserted / total_events)
                        if estimated_inserted > 0:
                            ANALYTICS_EVENTS_INSERTED_TOTAL.labels(event_type=event_type).inc(
                                estimated_inserted
                            )

            if duplicates > 0:
                ANALYTICS_EVENTS_DUPLICATES_TOTAL.inc(duplicates)

            duration = time.time() - start_time
            ANALYTICS_BATCH_INSERT_DURATION_SECONDS.observe(duration)

            logger.info(
                "analytics.batch_inserted",
                total=len(db_events),
                inserted=inserted,
                duplicates=duplicates,
                duration_ms=int(duration * 1000),
            )

        except Exception as exc:
            await session.rollback()
            logger.error(
                "analytics.db_insert_error",
                error=str(exc),
                event_count=len(db_events),
                exc_info=True,
            )
            raise
