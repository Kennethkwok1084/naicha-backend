from __future__ import annotations

from prometheus_client import Counter

LOYALTY_POINTS_AWARDED_TOTAL = Counter(
    "loyalty_points_awarded_total",
    "Total loyalty points awarded after payment.",
    ["reason"],
)

COUPON_ISSUED_TOTAL = Counter(
    "coupon_issued_total",
    "Coupons issued through loyalty automation.",
    ["reason"],
)

__all__ = ["COUPON_ISSUED_TOTAL", "LOYALTY_POINTS_AWARDED_TOTAL"]
