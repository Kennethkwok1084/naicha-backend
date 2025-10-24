from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings, get_settings
from app.metrics.loyalty import COUPON_ISSUED_TOTAL, LOYALTY_POINTS_AWARDED_TOTAL
from app.models.accounts import Coupon, LoyaltyTransaction, User
from app.models.orders import Order

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
        self._logger = get_logger(__name__)

    async def award_on_payment(self, order: Order, *, skip_duplicate_check: bool = False) -> None:
        """支付成功后累积积分并在满足条件时自动发券。"""
        if order.user_id is None:
            return

        if not skip_duplicate_check:
            already_awarded = await self._session.scalar(
                select(LoyaltyTransaction.id).where(
                    LoyaltyTransaction.user_id == order.user_id,
                    LoyaltyTransaction.order_id == order.order_id,
                    LoyaltyTransaction.reason == ORDER_PAID_REASON,
                )
            )
            if already_awarded is not None:
                return

        points = self._calculate_points(order)
        if points <= 0:
            return

        stmt = select(User).where(User.user_id == order.user_id)
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        user_row = result.scalar_one_or_none()
        if user_row is None:
            return

        starting_points = int(user_row.loyalty_points or 0)
        points_value = int(points)
        threshold = self.COUPON_THRESHOLD

        augmented_points = starting_points + points_value
        if threshold > 0:
            coupons_to_issue = augmented_points // threshold
            remaining_points = augmented_points % threshold
        else:
            coupons_to_issue = 0
            remaining_points = augmented_points

        user_row.loyalty_points = remaining_points
        self._logger.debug(
            "loyalty.award_on_payment_summary",
            order_id=order.order_id,
            user_id=user_row.user_id,
            points_awarded=points_value,
            coupons_to_issue=coupons_to_issue,
            augmented_points=augmented_points,
            final_points=remaining_points,
        )

        self._session.add(
            LoyaltyTransaction(
                user_id=user_row.user_id,
                order_id=order.order_id,
                delta_points=points_value,
                reason=ORDER_PAID_REASON,
            )
        )
        LOYALTY_POINTS_AWARDED_TOTAL.labels(reason=ORDER_PAID_REASON).inc(points_value)

        for _ in range(coupons_to_issue):
            await self._issue_coupon(user_row.user_id)

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

    async def _issue_coupon(self, user_id: int) -> None:
        self._session.add(
            LoyaltyTransaction(
                user_id=user_id,
                order_id=None,
                delta_points=-self.COUPON_THRESHOLD,
                reason=COUPON_GRANT_REASON,
            )
        )
        self._session.add(
            Coupon(
                user_id=user_id,
                type=COUPON_TYPE,
                status="active",
                issued_at=datetime.now(tz=UTC),
            )
        )
        COUPON_ISSUED_TOTAL.labels(reason=COUPON_METRIC_REASON).inc()
