from __future__ import annotations

from prometheus_client import Counter

PAYMENT_MATCH_ATTEMPT_TOTAL = Counter(
    "payment_match_attempt_total",
    "Number of admin payment match attempts grouped by result.",
    ["result"],
)

__all__ = ["PAYMENT_MATCH_ATTEMPT_TOTAL"]
