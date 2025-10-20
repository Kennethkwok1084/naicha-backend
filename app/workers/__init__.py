from __future__ import annotations

import asyncio
import threading

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
    except Exception:
        logger.exception("print_job.enqueue_unexpected_error", job_id=job_id)

    _dispatch_local(job_id)


def _dispatch_local(job_id: int) -> None:
    async def _run_job() -> None:
        try:
            await execute_print_job(job_id)
        except Exception as exc:  # pragma: no cover - 已在线程中记录
            logger.exception("print_job.local_execution_failed", job_id=job_id, error=str(exc))

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_run_job())
    else:
        thread = threading.Thread(target=lambda: asyncio.run(_run_job()), daemon=True)
        thread.start()


__all__ = ["enqueue_print_job", "get_celery_app", "process_print_job"]
