from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings, get_settings
from app.metrics.loyalty import COUPON_ISSUED_TOTAL, LOYALTY_POINTS_AWARDED_TOTAL
from app.models.accounts import Coupon, LoyaltyTransaction, User
from app.models.orders import Order, OrderItem

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

        total_cups = await self._get_order_cups(order.order_id)
        points = self._calculate_points(total_cups)
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
            cups_awarded=total_cups,
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

    async def _get_order_cups(self, order_id: int | None) -> int:
        if order_id is None:
            return 0

        result = await self._session.execute(
            select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(OrderItem.order_id == order_id)
        )
        cups = result.scalar_one()
        return int(cups or 0)

    def _calculate_points(self, total_cups: int) -> int:
        if total_cups <= 0:
            return 0

        ratio = Decimal(str(self._settings.loyalty_points_ratio))
        if ratio <= 0:
            return 0

        raw_points = (Decimal(total_cups) * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN)
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

    async def get_transactions(
        self, user_id: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[LoyaltyTransaction], int]:
        """获取用户积分明细"""
        # 查询总数
        count_stmt = select(func.count()).select_from(LoyaltyTransaction).where(
            LoyaltyTransaction.user_id == user_id
        )
        total_count = await self._session.scalar(count_stmt) or 0

        # 查询明细
        stmt = (
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.user_id == user_id)
            .order_by(LoyaltyTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        transactions = list(result.scalars().all())

        return transactions, int(total_count)

    async def get_coupons(
        self, user_id: int, *, status_filter: str | None = None
    ) -> tuple[list[Coupon], dict[str, int]]:
        """获取用户优惠券列表"""
        # 构建查询
        stmt = select(Coupon).where(Coupon.user_id == user_id)
        if status_filter:
            stmt = stmt.where(Coupon.status == status_filter)
        stmt = stmt.order_by(Coupon.created_at.desc())

        result = await self._session.execute(stmt)
        coupons = list(result.scalars().all())

        # 统计各状态数量
        count_stmt = (
            select(Coupon.status, func.count())
            .where(Coupon.user_id == user_id)
            .group_by(Coupon.status)
        )
        count_result = await self._session.execute(count_stmt)
        counts = dict(count_result.all())

        stats = {
            "active_count": counts.get("active", 0),
            "used_count": counts.get("used", 0),
            "total_count": sum(counts.values()),
        }

        return coupons, stats

    async def use_coupon(self, coupon_id: int, user_id: int, order_id: int) -> Coupon:
        """使用优惠券"""
        # 查询优惠券并加锁
        stmt = select(Coupon).where(
            Coupon.coupon_id == coupon_id, Coupon.user_id == user_id
        )
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        coupon = result.scalar_one_or_none()

        if coupon is None:
            raise CouponNotFoundError(f"Coupon {coupon_id} not found or not owned by user.")

        if coupon.status != "active":
            raise CouponInvalidError(f"Coupon {coupon_id} is not active (status={coupon.status}).")

        # 标记为已使用
        coupon.status = "used"
        coupon.used_at = datetime.now(tz=UTC)
        coupon.used_in_order_id = order_id

        self._logger.info(
            "loyalty.coupon_used",
            coupon_id=coupon_id,
            user_id=user_id,
            order_id=order_id,
        )

        return coupon


class CouponNotFoundError(Exception):
    """优惠券不存在或不属于用户"""


class CouponInvalidError(Exception):
    """优惠券无效(已使用/过期/作废)"""
