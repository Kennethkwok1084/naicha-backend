from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.models.orders import Order
from app.models.reservations import ReservationSlot
from app.services.shop import ShopService

logger = get_logger(__name__)


@dataclass(slots=True)
class ReservationPlan:
    scheduled_at_utc: datetime
    slot_id: int
    slot_start_utc: datetime
    slot_end_utc: datetime


class ReservationError(Exception):
    """预约相关通用异常。"""


class ReservationValidationError(ReservationError):
    """预约请求未通过校验。"""


class ReservationService:
    """预约场景的校验与定时任务。"""

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._logger = get_logger(__name__)

    async def plan(self, scheduled_at: datetime) -> ReservationPlan:
        """校验预约时间并返回 UTC 计划。"""
        if not self._settings.reservation_enabled:
            raise ReservationValidationError("预约功能未开启。")

        shop_service = ShopService(self._session, self._settings)
        profile = await shop_service.get_profile()

        timezone = profile.timezone or "Asia/Shanghai"
        tz = ZoneInfo(timezone)
        local_now = datetime.now(tz=tz)
        local_target = scheduled_at.astimezone(tz)

        if profile.open_hours_json:
            aligned = self._align_to_open_hours(local_target, tz, profile.open_hours_json)
            if aligned is None:
                raise ReservationValidationError("预约时间不在营业时间内。")
            local_target = aligned

        if local_target <= local_now:
            raise ReservationValidationError("预约时间必须晚于当前时间。")
        if local_target - local_now > timedelta(hours=24):
            raise ReservationValidationError("目前仅支持 24 小时内的预约。")

        lead_minutes = max(self._settings.reservation_reminder_minutes, 5)
        min_allowed = local_now + timedelta(minutes=lead_minutes)
        if local_target < min_allowed:
            raise ReservationValidationError(f"预约时间需至少提前 {lead_minutes} 分钟。")

        slot_minutes = max(self._settings.reservation_slot_granularity_minutes, 5)
        slot_start_local = self._floor_to_slot(local_target, slot_minutes)
        slot_end_local = slot_start_local + timedelta(minutes=slot_minutes)
        slot_start_utc = slot_start_local.astimezone(UTC)
        slot_end_utc = slot_end_local.astimezone(UTC)
        slot = await self._reserve_slot(slot_start_utc, slot_end_utc)

        return ReservationPlan(
            scheduled_at_utc=local_target.astimezone(UTC),
            slot_id=slot.slot_id,
            slot_start_utc=slot.slot_start,
            slot_end_utc=slot.slot_end,
        )

    async def send_due_reminders(self, now: datetime) -> list[int]:
        """查找需要发送提醒的预约订单并标记发送时间。"""
        if not self._settings.reservation_enabled:
            return []

        orders = await self._load_scheduled_orders()
        if not orders:
            return []

        reminder_delta = timedelta(minutes=self._settings.reservation_reminder_minutes)
        touched: list[Order] = []

        for order in orders:
            if order.reminder_sent_at is not None:
                continue
            if order.scheduled_at is None:
                continue
            if order.payment_status != "paid":
                continue
            if order.status != "paid":
                continue

            scheduled_utc = order.scheduled_at.astimezone(UTC)
            if scheduled_utc <= now:
                continue

            reminder_time = scheduled_utc - reminder_delta
            if reminder_time <= now < scheduled_utc:
                order.reminder_sent_at = now
                touched.append(order)

        if touched:
            await self._session.flush()
            order_ids = [order.order_id for order in touched]
            self._logger.info("reservation.reminder_marked", order_ids=order_ids)
            return order_ids
        return []

    async def activate_due_orders(self, now: datetime) -> list[int]:
        """将到点的预约订单切换到 in_production。"""
        if not self._settings.reservation_enabled:
            return []

        orders = await self._load_scheduled_orders()
        if not orders:
            return []

        progressed: list[Order] = []
        for order in orders:
            if order.scheduled_at is None:
                continue
            scheduled_utc = order.scheduled_at.astimezone(UTC)
            if scheduled_utc > now:
                continue
            if order.status != "paid" or order.payment_status != "paid":
                continue
            if order.status == "in_production":
                continue

            order.status = "in_production"
            order.updated_at = now
            progressed.append(order)

        if progressed:
            await self._session.flush()
            order_ids = [order.order_id for order in progressed]
            self._logger.info("reservation.activated", order_ids=order_ids)
            return order_ids
        return []

    async def _load_scheduled_orders(self) -> list[Order]:
        stmt = select(Order).where(
            Order.is_scheduled.is_(True),
            Order.scheduled_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def release_slot(self, slot_id: int | None) -> None:
        if not slot_id:
            return

        stmt = select(ReservationSlot).where(ReservationSlot.slot_id == slot_id)
        if self._dialect_name() != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        slot = result.scalar_one_or_none()
        if slot is None:
            return

        if slot.reserved_count <= 0:
            slot.reserved_count = 0
            slot.updated_at = datetime.now(tz=UTC)
            await self._session.flush()
            return

        slot.reserved_count -= 1
        slot.updated_at = datetime.now(tz=UTC)
        await self._session.flush()

    async def _reserve_slot(
        self,
        slot_start_utc: datetime,
        slot_end_utc: datetime,
    ) -> ReservationSlot:
        stmt = select(ReservationSlot).where(ReservationSlot.slot_start == slot_start_utc)
        if self._dialect_name() != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        slot = result.scalar_one_or_none()
        if slot is None:
            slot = ReservationSlot(
                slot_start=slot_start_utc,
                slot_end=slot_end_utc,
                capacity=max(self._settings.reservation_slot_capacity, 1),
                reserved_count=0,
            )
            self._session.add(slot)
            await self._session.flush()
        else:
            slot.slot_end = slot_end_utc

        if slot.reserved_count >= slot.capacity:
            raise ReservationValidationError("该预约时间段已满,请选择其他时间。")

        slot.reserved_count += 1
        slot.updated_at = datetime.now(tz=UTC)
        await self._session.flush()
        return slot

    def _dialect_name(self) -> str:
        bind = self._session.get_bind()
        if bind is None or not bind.dialect:
            return ""
        return getattr(bind.dialect, "name", "")

    @staticmethod
    def _within_open_hours(target: datetime, open_hours: Iterable[dict]) -> bool:
        weekday = target.isoweekday()
        for start, end in ReservationService._iter_ranges_for_weekday(open_hours, weekday):
            start_dt = datetime.combine(target.date(), start, tzinfo=target.tzinfo)
            end_dt = datetime.combine(target.date(), end, tzinfo=target.tzinfo)
            if start_dt <= target <= end_dt:
                return True
        return False

    @staticmethod
    def _align_to_open_hours(
        target: datetime,
        tz: ZoneInfo,
        open_hours: Iterable[dict],
    ) -> datetime | None:
        if ReservationService._within_open_hours(target, open_hours):
            return target

        # 尝试当天剩余档期
        for start, end in ReservationService._iter_ranges_for_weekday(
            open_hours, target.isoweekday()
        ):
            start_dt = datetime.combine(target.date(), start, tzinfo=tz)
            end_dt = datetime.combine(target.date(), end, tzinfo=tz)
            if target <= end_dt:
                return start_dt if target < start_dt else target

        # 尝试次日最早档期
        next_day = target.date() + timedelta(days=1)
        weekday = ((target.isoweekday()) % 7) + 1
        for start, _ in ReservationService._iter_ranges_for_weekday(open_hours, weekday):
            return datetime.combine(next_day, start, tzinfo=tz)

        return None

    @staticmethod
    def _iter_ranges_for_weekday(
        open_hours: Iterable[dict], weekday: int
    ) -> list[tuple[time, time]]:
        ranges: list[tuple[time, time]] = []
        entries = list(open_hours or [])
        for entry in entries:
            try:
                if int(entry.get("weekday")) != weekday:
                    continue
            except (TypeError, ValueError):
                continue

            for time_range in entry.get("ranges") or []:
                if not isinstance(time_range, (list, tuple)) or len(time_range) != 2:
                    continue
                start = ReservationService._parse_time(time_range[0])
                end = ReservationService._parse_time(time_range[1])
                if start is None or end is None:
                    continue
                ranges.append((start, end))

        ranges.sort()
        if ranges:
            return ranges

        # 无匹配 weekday 时, 兜底使用第一条配置
        for entry in entries:
            for time_range in entry.get("ranges") or []:
                if not isinstance(time_range, (list, tuple)) or len(time_range) != 2:
                    continue
                start = ReservationService._parse_time(time_range[0])
                end = ReservationService._parse_time(time_range[1])
                if start is None or end is None:
                    continue
                ranges.append((start, end))
        ranges.sort()
        return ranges

    @staticmethod
    def _floor_to_slot(target: datetime, slot_minutes: int) -> datetime:
        slot_minutes = max(slot_minutes, 1)
        minute = (target.minute // slot_minutes) * slot_minutes
        return target.replace(minute=minute, second=0, microsecond=0)

    @staticmethod
    def _parse_time(value: object) -> time | None:
        if not isinstance(value, str):
            return None
        try:
            hour_str, minute_str = value.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
            if 0 <= hour < 24 and 0 <= minute < 60:
                return time(hour=hour, minute=minute)
        except (ValueError, TypeError):
            return None
        return None
