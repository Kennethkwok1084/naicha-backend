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
        "app.workers.tasks.run_print_job_recovery": {"queue": settings.print_job_queue_name},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

beat_schedule = dict(getattr(celery_app.conf, "beat_schedule", {}))
beat_schedule.setdefault(
    "print_jobs_recovery",
    {
        "task": "app.workers.tasks.run_print_job_recovery",
        "schedule": settings.print_recovery_interval_seconds,
    },
)
beat_schedule.setdefault(
    "reservation_send_reminders",
    {
        "task": "app.workers.tasks.reservation_send_reminders",
        "schedule": 60,
    },
)
beat_schedule.setdefault(
    "reservation_activate_due_orders",
    {
        "task": "app.workers.tasks.reservation_activate_due_orders",
        "schedule": 60,
    },
)
beat_schedule.setdefault(
    "daily_reconciliation",
    {
        "task": "app.workers.tasks.run_daily_reconciliation",
        "schedule": 86400,
        "options": {"expires": 3600},
    },
)
celery_app.conf.beat_schedule = beat_schedule

celery_app.autodiscover_tasks(["app.workers"])
