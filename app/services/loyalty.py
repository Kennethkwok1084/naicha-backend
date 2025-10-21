from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import Coupon, LoyaltyTransaction, User
from app.models.orders import Order
from app.core.settings import Settings, get_settings
from app.metrics.loyalty import COUPON_ISSUED_TOTAL, LOYALTY_POINTS_AWARDED_TOTAL

ORDER_PAID_REASON: Final = "order_paid"
COUPON_GRANT_REASON: Final = "coupon_grant"
COUPON_TYPE: Final = "free_any_drink"
COUPON_METRIC_REASON: Final = "loyalty10"


class LoyaltyService:
    """处理会员积分累计与自动发券。"""

    COUPON_THRESHOLD: Final[int] = 10

    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

    async def award_on_payment(self, order: Order) -> None:
        """支付成功后累积积分并在满足条件时自动发券。"""
        if order.user_id is None:
            return

        already_awarded = await self._session.scalar(
            select(LoyaltyTransaction.id).where(
                LoyaltyTransaction.user_id == order.user_id,
                LoyaltyTransaction.order_id == order.order_id,
                LoyaltyTransaction.reason == ORDER_PAID_REASON,
            )
        )
        if already_awarded is not None:
            return

        user = await self._session.scalar(
            select(User)
            .where(User.user_id == order.user_id)
            .with_for_update()
        )
        if user is None:
            return

        points = self._calculate_points(order)
        if points <= 0:
            return

        self._session.add(
            LoyaltyTransaction(
                user_id=user.user_id,
                order_id=order.order_id,
                delta_points=points,
                reason=ORDER_PAID_REASON,
            )
        )
        user.loyalty_points += points
        LOYALTY_POINTS_AWARDED_TOTAL.labels(reason=ORDER_PAID_REASON).inc(points)

        coupons_to_issue = user.loyalty_points // self.COUPON_THRESHOLD
        for _ in range(coupons_to_issue):
            await self._issue_coupon(user)

    def _calculate_points(self, order: Order) -> int:
        ratio = Decimal(str(self._settings.loyalty_points_ratio))
        if ratio <= 0:
            return 0

        amount = Decimal(str(order.total_price or 0))
        if amount <= 0:
            return 0

        minimum = Decimal(str(self._settings.loyalty_points_min_order))
        if minimum and amount < minimum:
            return 0

        raw_points = (amount * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return int(raw_points)

    async def _issue_coupon(self, user: User) -> None:
        user.loyalty_points -= self.COUPON_THRESHOLD

        self._session.add(
            LoyaltyTransaction(
                user_id=user.user_id,
                order_id=None,
                delta_points=-self.COUPON_THRESHOLD,
                reason=COUPON_GRANT_REASON,
            )
        )
        self._session.add(
            Coupon(
                user_id=user.user_id,
                type=COUPON_TYPE,
                status="active",
                issued_at=datetime.now(tz=UTC),
            )
        )
        COUPON_ISSUED_TOTAL.labels(reason=COUPON_METRIC_REASON).inc()
