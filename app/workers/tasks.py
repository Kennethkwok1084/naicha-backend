from __future__ import annotations

import asyncio

from celery.utils.log import get_task_logger

from app.core.settings import get_settings
from app.workers.celery_app import celery_app
from app.workers.print_jobs import RetryablePrintJobError, execute_print_job

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
