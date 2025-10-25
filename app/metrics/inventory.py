from __future__ import annotations

from prometheus_client import Counter, Gauge

INVENTORY_DEDUCTION_TOTAL = Counter(
    "inventory_deduction_total",
    "库存扣减尝试的结果分布。",
    ["result"],  # success, insufficient, restored
)

INVENTORY_OVERSELL_TOTAL = Counter(
    "inventory_oversell_total",
    "检测到的超卖尝试次数,按商品聚合。",
    ["product_id"],
)

INVENTORY_CURRENT_STOCK = Gauge(
    "inventory_current_stock",
    "当前商品库存量快照。",
    ["product_id"],
)

__all__ = [
    "INVENTORY_CURRENT_STOCK",
    "INVENTORY_DEDUCTION_TOTAL",
    "INVENTORY_OVERSELL_TOTAL",
]
