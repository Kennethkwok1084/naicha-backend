from __future__ import annotations

from prometheus_client import Counter

ADMIN_LOGIN_TOTAL = Counter(
    "admin_login_total",
    "管理员登录请求计数",
    ["result"],  # success, failure
)

USER_LOGIN_TOTAL = Counter(
    "user_login_total",
    "用户登录请求计数（微信小程序 code 兑换）",
    ["result"],  # success, failure
)

__all__ = ["ADMIN_LOGIN_TOTAL", "USER_LOGIN_TOTAL"]
