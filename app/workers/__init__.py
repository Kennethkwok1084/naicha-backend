from __future__ import annotations

import asyncio

from celery import Celery
from celery.exceptions import CeleryError
from structlog import get_logger

from app.workers.celery_app import celery_app
from app.workers.print_jobs import execute_print_job
from app.workers.tasks import process_print_job

logger = get_logger(__name__)


def get_celery_app() -> Celery:
    return celery_app


def enqueue_print_job(job_id: int) -> None:
    try:
        process_print_job.apply_async(args=(job_id,))
        return
    except CeleryError as exc:
        logger.error("print_job.enqueue_failed", job_id=job_id, error=str(exc))
    except Exception as exc:
        logger.exception("print_job.enqueue_unexpected_error", job_id=job_id)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(execute_print_job(job_id))
    else:
        asyncio.run(execute_print_job(job_id))


__all__ = ["enqueue_print_job", "get_celery_app", "process_print_job"]
