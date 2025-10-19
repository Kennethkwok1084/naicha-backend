from __future__ import annotations

from celery import Celery

from app.core.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "naicha",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_default_queue=settings.celery_default_queue,
    task_routes={
        "app.workers.tasks.process_print_job": {"queue": settings.print_job_queue_name},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
celery_app.autodiscover_tasks(["app.workers"])
