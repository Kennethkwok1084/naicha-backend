from __future__ import annotations

import json
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.models.shop import ShopProfile, ShopSetting


class ShopProfileNotConfiguredError(Exception):
    """Raised when shop profile is missing required configuration."""


logger = get_logger(__name__)
_SHOP_PROFILE_CLIENT: Redis | None = None


class ShopService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    def _get_profile_cache_client(self) -> Redis | None:
        global _SHOP_PROFILE_CLIENT
        cache_url = self._settings.shop_profile_cache_url
        if not cache_url:
            return None
        if _SHOP_PROFILE_CLIENT is None:
            try:
                _SHOP_PROFILE_CLIENT = from_url(cache_url, decode_responses=True)
            except Exception as exc:  # pragma: no cover - 初始化失败仅记录
                logger.warning("shop.profile.cache_client_init_failed", error=str(exc))
                return None
        return _SHOP_PROFILE_CLIENT

    def _resolve_profile_file(self) -> Path:
        raw_path = Path(self._settings.shop_profile_file)
        if not raw_path.is_absolute():
            base_dir = Path(__file__).resolve().parents[2]
            raw_path = base_dir / raw_path
        return raw_path

    async def get_profile_snapshot(self) -> dict[str, Any]:
        cached_payload = await self._read_profile_from_cache()
        if cached_payload is not None:
            # 合并数据库配置
            await self._merge_settings_to_snapshot(cached_payload)
            return cached_payload

        file_payload = self._read_profile_from_file()
        if file_payload is not None:
            # 合并数据库配置
            await self._merge_settings_to_snapshot(file_payload)
            return file_payload

        raise ShopProfileNotConfiguredError("Shop profile snapshot 不存在。")

    async def _merge_settings_to_snapshot(self, snapshot: dict[str, Any]) -> None:
        """从数据库读取 shop_settings 并合并到快照中"""
        settings_dict = await self._get_shop_settings_dict()

        # 如果快照中没有这些字段，才从数据库读取（快照优先）
        if "min_delivery_amount" not in snapshot:
            snapshot["min_delivery_amount"] = settings_dict.get("min_delivery_amount")
        if "delivery_fee" not in snapshot:
            snapshot["delivery_fee"] = settings_dict.get("delivery_fee")
        if "free_delivery_amount" not in snapshot:
            snapshot["free_delivery_amount"] = settings_dict.get("free_delivery_amount")

    async def _get_shop_settings_dict(self) -> dict[str, str]:
        """读取 shop_settings 表的所有配置，返回 key-value 字典"""
        result = await self._session.execute(select(ShopSetting))
        settings = result.scalars().all()
        return {s.key: s.value for s in settings if s.value is not None}

    async def _read_profile_from_cache(self) -> dict[str, Any] | None:
        client = self._get_profile_cache_client()
        if client is None:
            return None
        try:
            raw_value = await client.get(self._settings.shop_profile_cache_key)
        except RedisError as exc:
            logger.warning("shop.profile.cache_read_failed", error=str(exc))
            return None

        if raw_value is None:
            return None

        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ShopProfileNotConfiguredError("Shop profile snapshot 格式错误。") from exc

        if not isinstance(payload, dict):
            raise ShopProfileNotConfiguredError("Shop profile snapshot 内容需为对象。")

        return payload

    def _read_profile_from_file(self) -> dict[str, Any] | None:
        file_path = self._resolve_profile_file()
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            payload = json.loads(content)
        except OSError as exc:
            raise ShopProfileNotConfiguredError("读取 shop profile snapshot 失败。") from exc
        except json.JSONDecodeError as exc:
            raise ShopProfileNotConfiguredError("Shop profile snapshot 格式错误。") from exc

        if not isinstance(payload, dict):
            raise ShopProfileNotConfiguredError("Shop profile snapshot 内容需为对象。")

        return payload

    async def get_profile(self) -> ShopProfile:
        profile = await self._session.get(ShopProfile, 1)
        if not profile:
            profile = ShopProfile()
            self._session.add(profile)
            await self._session.flush()
            await self._session.refresh(profile)
        return profile

    async def get_status_payload(self) -> dict[str, object]:
        profile = await self.get_profile()
        delivery_radius = profile.delivery_radius_m or self._settings.delivery_radius_m

        location = None
        if profile.location_lat is not None and profile.location_lng is not None:
            location = {
                "lat": profile.location_lat,
                "lng": profile.location_lng,
            }

        # 生成今日营业时间文案
        business_hours_today = self._get_business_hours_today(
            profile.is_open, profile.open_hours_json, profile.timezone
        )

        return {
            "is_open": profile.is_open,
            "delivery_radius_m": delivery_radius,
            "timezone": profile.timezone,
            "open_hours": profile.open_hours_json,
            "location": location,
            "features": {
                "multi_category_enabled": self._settings.multi_category_enabled,
                "reservation_enabled": self._settings.reservation_enabled,
                "want_enabled": self._settings.want_enabled,
            },
            "business_hours_today": business_hours_today,
        }

    def _get_business_hours_today(
        self, is_open: bool, open_hours_json: dict | None, timezone_str: str
    ) -> str | None:
        """生成今日营业时间可读文案"""
        if not open_hours_json:
            return "营业中" if is_open else "休息中"

        try:
            tz = ZoneInfo(timezone_str)
            now = datetime.now(tz)
            weekday = now.isoweekday()  # 1=周一, 7=周日

            # 查找今日营业时间
            for day_config in open_hours_json:
                if day_config.get("weekday") == weekday:
                    ranges = day_config.get("ranges", [])
                    if ranges:
                        # 取第一个时间段
                        first_range = ranges[0]
                        if len(first_range) >= 2:
                            start, end = first_range[0], first_range[1]
                            if is_open:
                                return f"营业中 {start}-{end}"
                            else:
                                return f"休息中 (营业时间 {start}-{end})"

            return "营业中" if is_open else "休息中"
        except Exception:
            # 解析失败时返回简单状态
            return "营业中" if is_open else "休息中"

    async def check_delivery(self, lat: float, lng: float) -> tuple[bool, float]:
        profile = await self.get_profile()
        if profile.location_lat is None or profile.location_lng is None:
            raise ShopProfileNotConfiguredError("Shop location not configured.")

        distance = self._haversine_distance(
            profile.location_lat,
            profile.location_lng,
            lat,
            lng,
        )
        delivery_radius = profile.delivery_radius_m or self._settings.delivery_radius_m
        # 20 米缓冲
        deliverable = distance <= (delivery_radius + 20)
        return deliverable, distance

    @staticmethod
    def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        radius = 6371000.0
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return radius * c
