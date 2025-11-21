from __future__ import annotations

from prometheus_client import Counter

GUEST_SESSION_CREATED_TOTAL = Counter(
    "guest_session_created_total",
    "游客会话创建或续期计数",
    ["result"],  # success, error
)

__all__ = ["GUEST_SESSION_CREATED_TOTAL"]
