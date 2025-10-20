from __future__ import annotations

import asyncio
from datetime import datetime

from celery.utils.log import get_task_logger

from app.core.settings import Settings, get_settings
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
    try:
        asyncio.run(execute_print_job(job_id, settings=settings))
    except RetryablePrintJobError as exc:
        logger.warning("print_job.retry_requested", job_id=job_id, message=str(exc))
        raise
    except Exception as exc:
        logger.exception("print_job.unhandled_exception", job_id=job_id)
        raise exc


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
    try:
        job_ids = asyncio.run(trigger_print_job_recovery(limit=limit))
        if job_ids:
            logger.info("print_job.recovery_enqueued", job_ids=job_ids)
    except Exception as exc:  # pragma: no cover
        logger.exception("print_job.recovery_failed", error=str(exc))
