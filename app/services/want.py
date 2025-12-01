from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import ClassVar
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.metrics.want import ADMIN_WANT_STATS_LATENCY_MS, WANT_EVENT_TOTAL
from app.models.accounts import User
from app.models.catalog import Product
from app.models.orders import WantEvent


class WantServiceError(Exception):
    """想要服务基础异常。"""


class WantFeatureDisabledError(WantServiceError):
    """想要功能未开启。"""


class WantTargetNotFoundError(WantServiceError):
    """目标商品不存在或不可用。"""


class WantRateLimitError(WantServiceError):
    """触发频控限制。"""


class WantService:
    SUPPORTED_RANGES: ClassVar[dict[str, int]] = {"1d": 1, "7d": 7, "30d": 30}
    DEFAULT_RANGE: ClassVar[str] = "7d"
    TOP_LIMIT_DEFAULT: ClassVar[int] = 20

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def record_want(
        self,
        *,
        product_id: int,
        user: User | None,
        ip: str | None,
        user_agent: str | None,
        now: datetime | None = None,
    ) -> WantEvent:
        if not self._settings.want_enabled:
            raise WantFeatureDisabledError("Want feature is disabled.")

        product = await self._session.get(Product, product_id)
        if product is None or product.status != "active":
            raise WantTargetNotFoundError("Product not available for want tracking.")

        user_id = user.user_id if user else None
        ip_hash = self._hash_ip(ip)
        if user_id is None and ip_hash is None:
            raise WantServiceError("Unable to determine requester identity.")

        now_utc = now or datetime.now(tz=UTC)
        if await self._is_rate_limited(
            product_id=product_id,
            user_id=user_id,
            ip_hash=ip_hash,
            now=now_utc,
        ):
            raise WantRateLimitError("Want action allowed once per minute.")

        event = WantEvent(
            product_id=product_id,
            user_id=user_id,
            ip_hash=ip_hash,
            user_agent=user_agent,
        )
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)

        source_label = "user" if user_id is not None else "guest"
        WANT_EVENT_TOTAL.labels(source=source_label).inc()

        return event

    async def get_stats(
        self,
        *,
        range_key: str | None,
        limit: int | None = None,
        reference: datetime | None = None,
    ) -> dict[str, object]:
        started_at = perf_counter()
        days = self._resolve_range(range_key)
        limit = limit or self.TOP_LIMIT_DEFAULT
        limit = max(1, min(limit, 100))

        tz = ZoneInfo("Asia/Shanghai")
        reference_time = reference or datetime.now(tz=UTC)
        end_local = reference_time.astimezone(tz)
        start_local = (end_local - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_utc = start_local.astimezone(UTC)

        events = await self._fetch_events_since(start_utc)
        product_ids = {event.product_id for event in events}
        products_lookup = await self._load_product_names(product_ids)

        totals = Counter()
        daily_totals: dict[str, int] = defaultdict(int)
        for event in events:
            event_time = self._normalize_datetime(event.created_at)
            totals[event.product_id] += 1
            date_key = event_time.astimezone(tz).date().isoformat()
            daily_totals[date_key] += 1

        top_products = [
            {
                "product_id": product_id,
                "product_name": products_lookup.get(product_id),
                "total": totals_value,
            }
            for product_id, totals_value in totals.most_common(limit)
        ]

        series_dates = self._generate_date_range(start_local.date(), end_local.date())
        daily_series = [
            {"date": date.isoformat(), "count": daily_totals.get(date.isoformat(), 0)}
            for date in series_dates
        ]

        payload = {
            "range": range_key or self.DEFAULT_RANGE,
            "start": start_local.astimezone(UTC),
            "end": end_local.astimezone(UTC),
            "top_products": top_products,
            "daily_series": daily_series,
        }

        duration_ms = (perf_counter() - started_at) * 1000
        range_label = range_key or self.DEFAULT_RANGE
        ADMIN_WANT_STATS_LATENCY_MS.labels(range=range_label).observe(duration_ms)

        return payload

    async def _is_rate_limited(
        self,
        *,
        product_id: int,
        user_id: int | None,
        ip_hash: str | None,
        now: datetime,
    ) -> bool:
        cutoff = now - timedelta(minutes=1)
        stmt = select(WantEvent.id).where(
            WantEvent.product_id == product_id,
            WantEvent.created_at >= cutoff,
        )
        if user_id is not None:
            stmt = stmt.where(WantEvent.user_id == user_id)
        elif ip_hash is not None:
            stmt = stmt.where(WantEvent.ip_hash == ip_hash)
        else:
            return False

        stmt = stmt.limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _fetch_events_since(self, start: datetime) -> list[WantEvent]:
        stmt = (
            select(WantEvent)
            .where(WantEvent.created_at >= start)
            .order_by(WantEvent.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _load_product_names(self, product_ids: Iterable[int]) -> dict[int, str]:
        if not product_ids:
            return {}
        stmt = select(Product.product_id, Product.name).where(Product.product_id.in_(product_ids))
        result = await self._session.execute(stmt)
        return {row.product_id: row.name for row in result.all()}

    def _resolve_range(self, range_key: str | None) -> int:
        if not range_key:
            return self.SUPPORTED_RANGES[self.DEFAULT_RANGE]
        if range_key not in self.SUPPORTED_RANGES:
            raise ValueError("Unsupported range value.")
        return self.SUPPORTED_RANGES[range_key]

    @staticmethod
    def _generate_date_range(start: datetime.date, end: datetime.date) -> list[datetime.date]:
        days = (end - start).days
        return [start + timedelta(days=offset) for offset in range(days + 1)]

    def _hash_ip(self, ip: str | None) -> str | None:
        if not ip:
            return None
        payload = f"{ip}|{self._settings.secret_key}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
