from __future__ import annotations

from prometheus_client import Counter, Histogram

ADMIN_ORDER_CREATED_TOTAL = Counter(
    "admin_order_created_total",
    "Number of POS orders created by admins.",
    ["channel", "result"],
)

ADMIN_ORDER_CREATE_LATENCY_MS = Histogram(
    "admin_order_create_latency_ms",
    "Latency for POS order creation handled by admin endpoints.",
    ["channel"],
    buckets=(25, 50, 75, 100, 150, 200, 300, 500, 1000),
)


__all__ = ["ADMIN_ORDER_CREATED_TOTAL", "ADMIN_ORDER_CREATE_LATENCY_MS"]
