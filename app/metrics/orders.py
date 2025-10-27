from __future__ import annotations

from prometheus_client import Counter, Histogram

ORDER_CREATE_TOTAL = Counter(
    "order_create_total",
    "订单创建处理结果计数。",
    ["result"],
)

ORDER_AUTO_CANCEL_TOTAL = Counter(
    "orders_auto_cancelled_total",
    "自动取消订单触发次数,按来源区分。",
    ["source", "result"],
)

ORDER_AUTO_CANCEL_DELAY_SECONDS = Histogram(
    "orders_auto_cancel_delay_seconds",
    "订单从创建到被自动取消的耗时(秒)。",
    ["source"],
    buckets=(
        60,
        120,
        300,
        600,
        900,
        1200,
        1800,
        3600,
        float("inf"),
    ),
)

__all__ = [
    "ORDER_AUTO_CANCEL_DELAY_SECONDS",
    "ORDER_AUTO_CANCEL_TOTAL",
    "ORDER_CREATE_TOTAL",
]
