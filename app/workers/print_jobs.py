from __future__ import annotations
from datetime import UTC, datetime, timedelta
from typing import Sequence

import httpx
from sqlalchemy import and_, case, or_, select
from structlog import get_logger

from app.core.settings import Settings, get_settings
from app.db.session import async_session_factory
from app.models.orders import Order, OrderItem, PrintJob

logger = get_logger(__name__)


class PrintJobError(Exception):
    """基础打印任务异常。"""


class RetryablePrintJobError(PrintJobError):
    """可重试异常，用于触发 Celery 自动重试。"""


class NonRetryablePrintJobError(PrintJobError):
    """不可重试异常，Worker 会记录失败并停止重试。"""


async def execute_print_job(job_id: int, settings: Settings | None = None) -> None:
    current_settings = settings or get_settings()
    async with async_session_factory() as session:
        job = await _acquire_job(session, job_id)
        if job is None:
            logger.warning("print_job.missing", job_id=job_id)
            return

        if job.status == "done":
            logger.info("print_job.already_done", job_id=job_id)
            return

        job.status = "processing"
        job.try_count += 1
        job.last_error = None
        job.next_try_at = None
        await session.commit()

        order = await session.get(Order, job.order_id)
        if order is None:
            job.status = "failed"
            job.last_error = "关联订单不存在"
            await session.commit()
            raise NonRetryablePrintJobError("关联订单不存在")

        items = await _load_order_items(session, order.order_id)
        printer = PrinterGateway(current_settings)

        try:
            await printer.dispatch(job, order, items)
        except NonRetryablePrintJobError as exc:
            job.status = "failed"
            job.last_error = str(exc)
            job.next_try_at = None
            await session.commit()
            logger.error("print_job.permanent_failure", job_id=job.job_id, error=job.last_error)
        except RetryablePrintJobError as exc:
            job.status = "failed"
            job.last_error = str(exc)
            job.next_try_at = datetime.now(tz=UTC) + _next_retry_delay(job.try_count)
            await session.commit()
            logger.warning(
                "print_job.retryable_failure",
                job_id=job.job_id,
                try_count=job.try_count,
                error=job.last_error,
            )
            raise
        except Exception as exc:
            job.status = "failed"
            job.last_error = f"unexpected_error: {exc}"
            job.next_try_at = datetime.now(tz=UTC) + _next_retry_delay(job.try_count)
            await session.commit()
            logger.exception("print_job.unexpected_failure", job_id=job.job_id)
            raise RetryablePrintJobError(job.last_error)
        else:
            job.status = "done"
            job.printed_at = datetime.now(tz=UTC)
            job.last_error = None
            job.next_try_at = None
            await session.commit()
            logger.info("print_job.completed", job_id=job.job_id)


async def _acquire_job(session, job_id: int) -> PrintJob | None:
    stmt = select(PrintJob).where(PrintJob.job_id == job_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _load_order_items(session, order_id: int) -> Sequence[OrderItem]:
    result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    return result.scalars().all()


async def recover_print_jobs(
    *,
    limit: int = 50,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> list[int]:
    reference_time = now or datetime.now(tz=UTC)
    current_settings = settings or get_settings()
    interval_seconds = max(current_settings.print_recovery_interval_seconds, 1)
    next_try_time = reference_time + timedelta(seconds=interval_seconds)
    jobs_table = PrintJob.__table__

    conditions = and_(
        or_(
            jobs_table.c.status == "pending",
            and_(jobs_table.c.status == "failed", jobs_table.c.next_try_at.is_not(None)),
        ),
        or_(jobs_table.c.next_try_at.is_(None), jobs_table.c.next_try_at <= reference_time),
    )

    if limit <= 0:
        return []

    nulls_rank = case(
        (jobs_table.c.next_try_at.is_(None), 0),
        else_=1,
    )

    candidate_stmt = (
        select(jobs_table.c.job_id)
        .where(conditions)
        .order_by(nulls_rank, jobs_table.c.next_try_at.asc(), jobs_table.c.job_id)
        .limit(limit)
    )

    update_stmt = (
        jobs_table.update()
        .where(jobs_table.c.job_id.in_(candidate_stmt))
        .values(
            next_try_at=next_try_time,
            status=case(
                (jobs_table.c.status == "failed", "pending"),
                else_=jobs_table.c.status,
            ),
        )
        .returning(jobs_table.c.job_id)
    )

    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(update_stmt)
            job_ids = [row[0] for row in result.fetchall()]

    job_ids.sort()
    return job_ids


def _next_retry_delay(try_count: int) -> timedelta:
    # 简单指数退避，但限定最大 15 分钟，避免对打印服务造成压力。
    base_seconds = 2 ** max(try_count - 1, 0)
    return timedelta(seconds=min(base_seconds, 900))


class PrinterGateway:
    def __init__(self, settings: Settings):
        self._settings = settings

    async def dispatch(
        self,
        job: PrintJob,
        order: Order,
        items: Sequence[OrderItem],
    ) -> None:
        if not self._settings.printer_webhook_url:
            logger.warning(
                "printer.webhook_not_configured",
                job_id=job.job_id,
            )
            return

        payload = self._build_payload(job, order, items)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._settings.printer_webhook_token:
            headers["Authorization"] = f"Bearer {self._settings.printer_webhook_token}"

        try:
            async with httpx.AsyncClient(timeout=self._settings.printer_timeout_seconds) as client:
                response = await client.post(
                    self._settings.printer_webhook_url,
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise RetryablePrintJobError(f"打印超时: {exc}") from exc
        except httpx.TransportError as exc:
            raise RetryablePrintJobError(f"打印传输异常: {exc}") from exc

        if 500 <= response.status_code < 600:
            raise RetryablePrintJobError(f"打印服务 5xx 响应: {response.status_code}")

        if response.status_code >= 400:
            raise NonRetryablePrintJobError(
                f"打印服务返回错误: {response.status_code} {response.text}"
            )

    @staticmethod
    def _build_payload(
        job: PrintJob,
        order: Order,
        items: Sequence[OrderItem],
    ) -> dict[str, object]:
        return {
            "job_id": job.job_id,
            "order": {
                "order_id": order.order_id,
                "order_number": order.order_number,
                "total_price": float(order.total_price),
                "notes": order.notes,
                "status": order.status,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            },
            "items": [
                {
                    "item_id": item.item_id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "selected_specs": item.selected_specs_json,
                }
                for item in items
            ],
        }
