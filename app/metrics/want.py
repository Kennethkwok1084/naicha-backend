from __future__ import annotations

from prometheus_client import Counter, Histogram

WANT_EVENT_TOTAL = Counter(
    "want_event_total",
    "Total number of want events recorded.",
    ["source"],
)

ADMIN_WANT_STATS_LATENCY_MS = Histogram(
    "admin_want_stats_latency_ms",
    "Latency of admin want stats aggregation in milliseconds.",
    ["range"],
    buckets=(10, 25, 50, 75, 100, 250, 500, 1000),
)

__all__ = ["ADMIN_WANT_STATS_LATENCY_MS", "WANT_EVENT_TOTAL"]
