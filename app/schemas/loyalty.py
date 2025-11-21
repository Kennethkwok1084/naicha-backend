from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LoyaltyTransactionSchema(BaseModel):
    """积分明细记录"""

    id: int
    user_id: int
    order_id: int | None
    delta_points: int
    reason: str
    created_at: datetime


class LoyaltyTransactionsResponseSchema(BaseModel):
    """积分明细列表响应"""

    transactions: list[LoyaltyTransactionSchema]
    total_count: int
    current_points: int
    limit: int
    offset: int


class CouponSchema(BaseModel):
    """优惠券"""

    coupon_id: int
    user_id: int
    type: str
    status: str
    meta_json: dict | None
    issued_at: datetime | None
    used_at: datetime | None
    used_in_order_id: int | None
    created_at: datetime


class CouponStatsSchema(BaseModel):
    """优惠券状态统计"""

    total_count: int
    active_count: int
    used_count: int
    expired_count: int
    void_count: int


class CouponsResponseSchema(BaseModel):
    """优惠券列表响应"""

    coupons: list[CouponSchema]
    stats: CouponStatsSchema


class StampStatusSchema(BaseModel):
    """集点状态"""

    total_completed_orders: int
    stamps_in_cycle: int
    rewards_available: int
    cycle_size: int = 10
