from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.models.maintenance import MaintenanceHeartbeat, MaintenanceJob
from app.services.orders import OrderService

logger = get_logger(__name__)


class MaintenanceServiceError(Exception):
    """Maintenance service base error."""


class MaintenanceJobNotFoundError(MaintenanceServiceError):
    """Raised when maintenance job is missing."""


class MaintenanceService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._logger = logger

    async def enqueue_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        run_after: datetime | None = None,
    ) -> MaintenanceJob:
        scheduled_at = run_after or datetime.now(tz=UTC)
        existing_stmt = (
            select(MaintenanceJob)
            .where(
                MaintenanceJob.job_type == job_type,
                MaintenanceJob.status == "pending",
            )
            .limit(1)
        )
        existing_result = await self._session.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

        job = MaintenanceJob(
            job_type=job_type,
            status="pending",
            payload_json=payload or {},
            scheduled_at=scheduled_at,
            attempts=0,
        )
        self._session.add(job)
        await self._session.flush()
        self._logger.info(
            "maintenance.job_enqueued",
            job_id=job.job_id,
            job_type=job.job_type,
            scheduled_at=scheduled_at.isoformat(),
        )
        return job

    async def acquire_jobs(
        self,
        *,
        job_type: str | None = None,
        limit: int = 5,
    ) -> list[int]:
        now = datetime.now(tz=UTC)
        stmt = (
            select(MaintenanceJob)
            .where(
                MaintenanceJob.status == "pending",
                MaintenanceJob.scheduled_at <= now,
            )
            .order_by(MaintenanceJob.scheduled_at)
            .limit(limit)
        )
        if job_type:
            stmt = stmt.where(MaintenanceJob.job_type == job_type)

        bind = self._session.get_bind()
        if bind is not None and getattr(bind.dialect, "name", "") != "sqlite":
            stmt = stmt.with_for_update(skip_locked=True)

        result = await self._session.execute(stmt)
        jobs = list(result.scalars().all())
        job_ids: list[int] = []
        for job in jobs:
            job.status = "running"
            job.started_at = now
            job.attempts = (job.attempts or 0) + 1
            job_ids.append(job.job_id)
        if jobs:
            await self._session.flush()
        return job_ids

    async def get_job(self, job_id: int) -> MaintenanceJob | None:
        return await self._session.get(MaintenanceJob, job_id)

    async def execute_job(self, job: MaintenanceJob) -> dict[str, Any]:
        if job.job_type == "cancel_stale_pending_orders":
            return await self._run_auto_cancel_job(job)
        raise MaintenanceServiceError(f"Unsupported maintenance job type: {job.job_type}")

    async def complete_job(self, job: MaintenanceJob, result: dict[str, Any]) -> None:
        now = datetime.now(tz=UTC)
        job.status = "completed"
        job.completed_at = now
        job.result_json = result
        job.last_error = None
        await self._session.flush()
        self._logger.info(
            "maintenance.job_completed",
            job_id=job.job_id,
            job_type=job.job_type,
            result=result,
        )

    async def fail_job(self, job: MaintenanceJob, error_message: str) -> None:
        now = datetime.now(tz=UTC)
        job.status = "failed"
        job.completed_at = now
        job.last_error = error_message[:500]
        await self._session.flush()
        self._logger.error(
            "maintenance.job_failed",
            job_id=job.job_id,
            job_type=job.job_type,
            error=job.last_error,
        )

    async def record_heartbeat(self, name: str, *, at: datetime | None = None) -> None:
        timestamp = at or datetime.now(tz=UTC)
        heartbeat = await self._session.get(MaintenanceHeartbeat, name)
        if heartbeat is None:
            heartbeat = MaintenanceHeartbeat(
                name=name,
                last_heartbeat=timestamp,
                updated_at=timestamp,
            )
            self._session.add(heartbeat)
        else:
            heartbeat.last_heartbeat = timestamp
            heartbeat.updated_at = timestamp
        await self._session.flush()

    async def get_heartbeat(self, name: str) -> MaintenanceHeartbeat | None:
        return await self._session.get(MaintenanceHeartbeat, name)

    async def _run_auto_cancel_job(self, job: MaintenanceJob) -> dict[str, Any]:
        payload = job.payload_json or {}
        limit = int(payload.get("limit") or 100)
        cutoff_minutes = int(
            payload.get("cutoff_minutes") or self._settings.order_pending_timeout_minutes
        )
        reason = payload.get("reason") or "auto_cancel.db_cron"
        cutoff_minutes = max(cutoff_minutes, 1)
        cutoff = datetime.now(tz=UTC) - timedelta(minutes=cutoff_minutes)

        order_service = OrderService(self._session, self._settings)
        cancelled_ids = await order_service.cancel_stale_pending_orders(
            cutoff,
            limit=limit,
            reason=reason,
            source="cron",
        )
        return {
            "cancelled_order_ids": cancelled_ids,
            "count": len(cancelled_ids),
        }


async def run_jobs(job_ids: Iterable[int], *, settings: Settings) -> None:
    from app.db.session import async_session_factory

    for job_id in job_ids:
        async with async_session_factory() as session:
            service = MaintenanceService(session, settings)
            async with session.begin():
                job = await service.get_job(job_id)
                if job is None:
                    continue
                try:
                    result = await service.execute_job(job)
                except Exception as exc:  # pragma: no cover - logged by fail_job
                    await service.fail_job(job, str(exc))
                else:
                    await service.complete_job(job, result)
