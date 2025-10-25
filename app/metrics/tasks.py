from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

CELERY_TASK_RUNTIME_SECONDS = Histogram(
    "celery_task_runtime_seconds",
    "Runtime of Celery tasks in seconds",
    ["task"],
    buckets=(1, 5, 10, 30, 60, 120, 300),
)

RESERVATION_REMINDER_TOTAL = Counter(
    "reservation_reminder_total",
    "Number of reservation reminders marked",
)

RESERVATION_ACTIVATED_TOTAL = Counter(
    "reservation_activated_total",
    "Number of reservation orders activated",
)

RECONCILIATION_RUN_TOTAL = Counter(
    "reconciliation_run_total",
    "Daily reconciliation execution count",
    ["result"],
)

RECONCILIATION_DIFF_GAUGE = Gauge(
    "reconciliation_diff_count",
    "Latest reconciliation difference counts",
    ["type"],
)

CELERY_BEAT_LAST_HEARTBEAT_TIMESTAMP = Gauge(
    "celery_beat_last_heartbeat_timestamp",
    "Last heartbeat timestamp reported by Celery beat (UTC epoch seconds).",
)


__all__ = [
    "CELERY_BEAT_LAST_HEARTBEAT_TIMESTAMP",
    "CELERY_TASK_RUNTIME_SECONDS",
    "RECONCILIATION_DIFF_GAUGE",
    "RECONCILIATION_RUN_TOTAL",
    "RESERVATION_ACTIVATED_TOTAL",
    "RESERVATION_REMINDER_TOTAL",
]
