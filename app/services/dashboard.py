from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, get_settings
from app.metrics.dashboard import DASHBOARD_QUERY_LATENCY_MS
from app.models.orders import Order, OrderItem

DashboardRange = Literal["day", "week", "month"]


@dataclass
class _CacheEntry:
    expires_at: datetime
    payload: dict[str, Any]


class _DashboardCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[str, _CacheEntry] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry and entry.expires_at > datetime.now(tz=UTC):
                return entry.payload
            return None

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        async with self._lock:
            self._entries[key] = _CacheEntry(
                expires_at=datetime.now(tz=UTC) + timedelta(seconds=ttl_seconds),
                payload=value,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


_cache = _DashboardCache()


class DashboardService:
    """负责生成商家看板统计数据。"""

    CACHE_TTL_SECONDS = 60
    TOP_PRODUCT_LIMIT = 5
    RANGE_TO_DAYS: dict[DashboardRange, int] = {"day": 1, "week": 7, "month": 30}

    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

    async def get_dashboard(
        self,
        range_key: DashboardRange,
        *,
        compare: bool = False,
    ) -> dict[str, Any]:
        self._ensure_valid_range(range_key)
        cache_key = f"{range_key}:{int(compare)}"

        cached = await _cache.get(cache_key)
        if cached:
            return cached

        start, end = self._calculate_window(range_key)
        with DASHBOARD_QUERY_LATENCY_MS.labels(range_key).time():
            summary = await self._fetch_summary(start, end)
            trend = await self._fetch_trend(range_key, start, end)
            top_products = await self._fetch_top_products(start, end)
            channel_split = await self._fetch_payment_channel_split(start, end)
            payload: dict[str, Any] = {
                "range": range_key,
                "summary": summary,
                "trend": trend,
                "top_products": top_products,
                "payment_channel_split": channel_split,
            }
            if compare:
                previous_start, previous_end = self._calculate_comparison_window(range_key, start, end)
                compare_summary = await self._fetch_summary(previous_start, previous_end)
                payload["compare_summary"] = compare_summary

        await _cache.set(cache_key, payload, self.CACHE_TTL_SECONDS)
        return payload

    async def invalidate_cache(self) -> None:
        await _cache.clear()

    # Summary helpers -------------------------------------------------
    async def _fetch_summary(self, start: datetime, end: datetime) -> dict[str, Any]:
        stmt: Select[tuple[int, float, float, float]] = select(
            func.count(Order.order_id),
            func.coalesce(func.sum(Order.total_price), 0),
            func.coalesce(func.avg(Order.total_price), 0),
            func.coalesce(
                func.sum(
                    case((Order.status == "refunded", Order.total_price), else_=0)
                ),
                0,
            ),
        ).where(
            Order.payment_status == "paid",
            Order.updated_at >= start,
            Order.updated_at < end,
        )
        result = await self._session.execute(stmt)
        order_count, gross_sales, avg_ticket, refund_amount = result.one()
        return {
            "order_count": int(order_count or 0),
            "gross_sales": float(gross_sales or 0),
            "avg_ticket": float(avg_ticket or 0),
            "refund_amount": float(refund_amount or 0),
        }

    async def _fetch_trend(
        self,
        range_key: DashboardRange,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        stmt = select(
            Order.updated_at,
            Order.total_price,
        ).where(
            Order.payment_status == "paid",
            Order.updated_at >= start,
            Order.updated_at < end,
        )

        result = await self._session.execute(stmt)
        rows = result.fetchall()
        buckets: dict[datetime, dict[str, float | int]] = defaultdict(
            lambda: {"gross_sales": 0.0, "order_count": 0}
        )

        bucket_size = (
            timedelta(hours=1) if range_key == "day" else timedelta(days=1)
        )

        for updated_at, total_price in rows:
            ts = self._normalize_timestamp(updated_at, bucket_size)
            buckets[ts]["gross_sales"] = float(buckets[ts]["gross_sales"]) + float(total_price or 0)
            buckets[ts]["order_count"] = int(buckets[ts]["order_count"]) + 1

        # ensure buckets sorted chronologically
        points = [
            {
                "ts": bucket.isoformat(),
                "gross_sales": float(values["gross_sales"]),
                "order_count": int(values["order_count"]),
            }
            for bucket, values in sorted(buckets.items())
        ]

        return points

    async def _fetch_top_products(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                OrderItem.product_id,
                OrderItem.product_name,
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price),
                    0,
                ),
            )
            .join(Order, Order.order_id == OrderItem.order_id)
            .where(
                Order.payment_status == "paid",
                Order.updated_at >= start,
                Order.updated_at < end,
            )
            .group_by(OrderItem.product_id, OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc(), func.sum(OrderItem.quantity * OrderItem.unit_price).desc())
            .limit(self.TOP_PRODUCT_LIMIT)
        )

        result = await self._session.execute(stmt)
        products = []
        for product_id, product_name, quantity, gross_sales in result:
            products.append(
                {
                    "product_id": product_id,
                    "name": product_name,
                    "quantity": int(quantity or 0),
                    "gross_sales": float(gross_sales or 0),
                }
            )
        return products

    async def _fetch_payment_channel_split(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                func.coalesce(Order.payment_channel, "unknown"),
                func.count(Order.order_id),
                func.coalesce(func.sum(Order.total_price), 0),
            )
            .where(
                Order.payment_status == "paid",
                Order.updated_at >= start,
                Order.updated_at < end,
            )
            .group_by(func.coalesce(Order.payment_channel, "unknown"))
            .order_by(func.count(Order.order_id).desc())
        )

        result = await self._session.execute(stmt)
        channels = []
        for channel, order_count, gross_sales in result:
            channels.append(
                {
                    "channel": channel or "unknown",
                    "order_count": int(order_count or 0),
                    "gross_sales": float(gross_sales or 0),
                }
            )
        return channels

    # Range helpers ---------------------------------------------------
    def _calculate_window(self, range_key: DashboardRange) -> tuple[datetime, datetime]:
        now = self._now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days = self.RANGE_TO_DAYS[range_key]
        start = start_of_today - timedelta(days=days - 1)
        return start, now

    def _calculate_comparison_window(
        self,
        range_key: DashboardRange,
        current_start: datetime,
        current_end: datetime,
    ) -> tuple[datetime, datetime]:
        days = self.RANGE_TO_DAYS[range_key]
        duration = timedelta(days=days)
        previous_end = current_start
        previous_start = previous_end - duration
        return previous_start, previous_end

    @staticmethod
    def _normalize_timestamp(value: datetime, bucket_size: timedelta) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        seconds = int(value.timestamp())
        bucket_seconds = int(bucket_size.total_seconds())
        normalized = seconds - (seconds % bucket_seconds)
        return datetime.fromtimestamp(normalized, tz=UTC)

    @staticmethod
    def _ensure_valid_range(range_key: str) -> None:
        if range_key not in ("day", "week", "month"):
            raise ValueError("Unsupported dashboard range.")

    def _now(self) -> datetime:
        return datetime.now(tz=UTC)
