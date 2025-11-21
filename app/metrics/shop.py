from __future__ import annotations

from prometheus_client import Counter, Histogram

SHOP_PROFILE_REQUEST_TOTAL = Counter(
    "shop_profile_request_total",
    "门店基础信息接口请求计数",
    ["result"],  # success, cache_miss, error
)

SHOP_STATUS_REQUEST_TOTAL = Counter(
    "shop_status_request_total",
    "门店营业状态接口请求计数",
    ["result"],  # success, error
)

DELIVERY_CHECK_TOTAL = Counter(
    "delivery_check_total",
    "配送范围校验请求计数",
    ["result"],  # deliverable, out_of_range, shop_closed
)

DELIVERY_CHECK_LATENCY_MS = Histogram(
    "delivery_check_latency_ms",
    "配送范围校验耗时（毫秒）",
    buckets=(5, 10, 25, 50, 100, 200, 500),
)

__all__ = [
    "DELIVERY_CHECK_LATENCY_MS",
    "DELIVERY_CHECK_TOTAL",
    "SHOP_PROFILE_REQUEST_TOTAL",
    "SHOP_STATUS_REQUEST_TOTAL",
]
