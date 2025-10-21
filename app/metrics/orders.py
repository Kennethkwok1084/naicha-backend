from __future__ import annotations

from prometheus_client import Counter

ORDER_CREATE_TOTAL = Counter(
    "order_create_total",
    "订单创建处理结果计数。",
    ["result"],
)

__all__ = ["ORDER_CREATE_TOTAL"]
