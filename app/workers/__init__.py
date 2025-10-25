from __future__ import annotations

import asyncio
import threading
from threading import BoundedSemaphore, Lock

from celery import Celery
from celery.exceptions import CeleryError
from structlog import get_logger

from app.core.settings import get_settings
from app.workers.celery_app import celery_app
from app.workers.print_jobs import execute_print_job
from app.workers.tasks import process_payment_side_effects, process_print_job

logger = get_logger(__name__)
settings = get_settings()

_fallback_semaphore: BoundedSemaphore | None = None
_fallback_semaphore_limit = 0
_fallback_semaphore_lock = Lock()


def get_celery_app() -> Celery:
    return celery_app


def enqueue_print_job(job_id: int) -> None:
    dispatch_mode = settings.print_dispatch_mode
    should_try_local = dispatch_mode == "local_only"

    if dispatch_mode in {"celery", "celery_with_local_fallback"}:
        try:
            process_print_job.apply_async(args=(job_id,))
            return
        except CeleryError as exc:
            logger.error("print_job.enqueue_failed", job_id=job_id, error=str(exc))
            should_try_local = dispatch_mode == "celery_with_local_fallback"
        except Exception:
            logger.exception("print_job.enqueue_unexpected_error", job_id=job_id)
            should_try_local = dispatch_mode == "celery_with_local_fallback"

    if not should_try_local:
        return

    _dispatch_local(job_id)


def _acquire_fallback_slot() -> BoundedSemaphore | None:
    global _fallback_semaphore, _fallback_semaphore_limit

    limit = max(int(settings.print_local_max_parallel), 0)
    if limit == 0:
        return None

    with _fallback_semaphore_lock:
        if _fallback_semaphore is None or _fallback_semaphore_limit != limit:
            _fallback_semaphore = BoundedSemaphore(limit)
            _fallback_semaphore_limit = limit
        semaphore = _fallback_semaphore

    acquired = semaphore.acquire(blocking=False)
    if not acquired:
        return None
    return semaphore


def _dispatch_local(job_id: int) -> None:
    semaphore = _acquire_fallback_slot()
    if semaphore is None:
        logger.warning("print_job.local_fallback_rejected", job_id=job_id)
        return

    async def _run_job() -> None:
        try:
            await execute_print_job(job_id)
        except Exception as exc:  # pragma: no cover - 已在线程中记录
            logger.exception("print_job.local_execution_failed", job_id=job_id, error=str(exc))
        finally:
            semaphore.release()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_run_job())
    else:
        thread = threading.Thread(target=lambda: asyncio.run(_run_job()), daemon=True)
        thread.start()

    logger.warning("print_job.local_dispatch_enqueued", job_id=job_id)


def enqueue_payment_side_effects(order_id: int, source: str) -> None:
    try:
        process_payment_side_effects.apply_async(kwargs={"order_id": order_id, "source": source})
    except CeleryError as exc:
        logger.error(
            "payment_side_effects.enqueue_failed",
            order_id=order_id,
            source=source,
            error=str(exc),
        )
    except Exception:
        logger.exception(
            "payment_side_effects.enqueue_unexpected_error",
            order_id=order_id,
            source=source,
        )


__all__ = [
    "enqueue_payment_side_effects",
    "enqueue_print_job",
    "get_celery_app",
    "process_payment_side_effects",
    "process_print_job",
]
