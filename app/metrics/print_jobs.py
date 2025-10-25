from __future__ import annotations

from prometheus_client import Counter, Histogram

PRINT_JOB_TOTAL = Counter(
    "print_job_total",
    "打印任务执行结果计数。",
    ["result"],  # success, missing, already_done, retry_limit, retry_scheduled, non_retryable_failure
)

PRINT_JOB_RETRY_COUNT = Histogram(
    "print_job_retry_count",
    "打印任务完成前经历的尝试次数分布。",
    buckets=(1, 2, 3, 5, 8, 13, float("inf")),
)

PRINT_JOB_RECOVERY_TOTAL = Counter(
    "print_job_recovery_total",
    "恢复任务重新入队打印任务的次数。",
    ["result"],  # recovered, empty
)

__all__ = [
    "PRINT_JOB_RECOVERY_TOTAL",
    "PRINT_JOB_RETRY_COUNT",
    "PRINT_JOB_TOTAL",
]
