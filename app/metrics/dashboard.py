from __future__ import annotations

from prometheus_client import Histogram

DASHBOARD_QUERY_LATENCY_MS = Histogram(
    "admin_dashboard_query_latency_ms",
    "Latency for admin dashboard queries.",
    ["range"],
    buckets=(25, 50, 75, 100, 150, 200, 300, 500, 1000, 2000),
)

__all__ = ["DASHBOARD_QUERY_LATENCY_MS"]
