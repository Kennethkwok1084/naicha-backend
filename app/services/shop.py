from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.shop import ShopProfile


class ShopProfileNotConfiguredError(Exception):
    """Raised when shop profile is missing required configuration."""


class ShopService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

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
        }

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
        a = (
            sin(dlat / 2) ** 2
            + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
        )
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return radius * c
