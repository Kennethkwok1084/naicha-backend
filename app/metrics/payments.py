from __future__ import annotations

from prometheus_client import Counter, Histogram

PAYMENT_MATCH_ATTEMPT_TOTAL = Counter(
    "payment_match_attempt_total",
    "Number of admin payment match attempts grouped by result.",
    ["result"],
)
PAYMENT_CALLBACK_TOTAL = Counter(
    "payment_callback_total",
    "微信支付通知处理次数按结果分类。",
    ["result"],
)
PAYMENT_CALLBACK_LATENCY_MS = Histogram(
    "payment_callback_latency_ms",
    "微信支付通知处理耗时（毫秒）。",
    buckets=(5, 10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120),
)

__all__ = [
    "PAYMENT_MATCH_ATTEMPT_TOTAL",
    "PAYMENT_CALLBACK_TOTAL",
    "PAYMENT_CALLBACK_LATENCY_MS",
]
