from __future__ import annotations

from prometheus_client import Counter

USER_PROFILE_REQUEST_TOTAL = Counter(
    "user_profile_request_total",
    "用户资料接口请求计数",
    ["result"],  # success, error
)

USER_ADDRESSES_REQUEST_TOTAL = Counter(
    "user_addresses_request_total",
    "用户地址簿接口请求计数",
    ["result"],  # success, error
)

USER_COUPONS_REQUEST_TOTAL = Counter(
    "user_coupons_request_total",
    "用户优惠券列表接口请求计数",
    ["result"],  # success, error
)

__all__ = [
    "USER_ADDRESSES_REQUEST_TOTAL",
    "USER_COUPONS_REQUEST_TOTAL",
    "USER_PROFILE_REQUEST_TOTAL",
]
