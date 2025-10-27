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
PAYMENT_CALLBACK_DUPLICATE_TOTAL = Counter(
    "payment_callback_duplicate_total",
    "支付平台重复回调次数(按渠道)。",
    ["channel"],
)
PAYMENT_CALLBACK_LATENCY_MS = Histogram(
    "payment_callback_latency_ms",
    "微信支付通知处理耗时(毫秒)。",
    buckets=(5, 10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120),
)

PAYMENT_SIDE_EFFECTS_TOTAL = Counter(
    "payment_side_effects_total",
    "支付链路异步副作用任务执行次数。",
    ["result", "source"],
)

__all__ = [
    "PAYMENT_CALLBACK_DUPLICATE_TOTAL",
    "PAYMENT_CALLBACK_LATENCY_MS",
    "PAYMENT_CALLBACK_TOTAL",
    "PAYMENT_MATCH_ATTEMPT_TOTAL",
    "PAYMENT_SIDE_EFFECTS_TOTAL",
]
