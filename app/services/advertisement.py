from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from structlog import get_logger

from app.core.settings import Settings, get_settings
from app.models.advertisement import AdCreative, AdPlacement, AdSlot
from app.schemas import (
    AdConfigCreativeSchema,
    AdConfigResponseSchema,
    AdCreativeCreateSchema,
    AdCreativeUpdateSchema,
    AdPlacementCreateSchema,
    AdPlacementOrderUpdateSchema,
    AdSlotCreateSchema,
    AdSlotUpdateSchema,
)

logger = get_logger(__name__)

_CONFIG_CACHE: dict[str, tuple[float, int, dict[str, list[dict[str, Any]]], datetime | None]] = {}
_CACHE_TTL_SECONDS = 300


class AdvertisementServiceError(Exception):
    """广告服务基础异常。"""


class AdSlotNotFoundError(AdvertisementServiceError):
    """广告位不存在。"""


class AdCreativeNotFoundError(AdvertisementServiceError):
    """素材不存在。"""


class AdPlacementConflictError(AdvertisementServiceError):
    """投放重复。"""


class AdPlacementNotFoundError(AdvertisementServiceError):
    """投放不存在。"""


class AdvertisementService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

    async def get_config(
        self,
        *,
        slots: Sequence[str],
        platform: str = "miniapp",
        current_version: int = 0,
    ) -> AdConfigResponseSchema:
        normalized_slots = tuple(sorted({slot.strip() for slot in slots if slot.strip()}))
        if not normalized_slots:
            return AdConfigResponseSchema(version=0, slots={})

        cache_key = self._build_cache_key(normalized_slots, platform)
        cached = _CONFIG_CACHE.get(cache_key)
        now_epoch = time.time()
        if cached:
            cached_created_at, cached_version, cached_payload, cached_next_change = cached
            cache_valid = now_epoch - cached_created_at < _CACHE_TTL_SECONDS
            if cached_next_change is not None:
                cache_valid = cache_valid and datetime.now(tz=UTC) < cached_next_change
            if cache_valid:
                payload = {
                    slot: [AdConfigCreativeSchema(**item) for item in creatives]
                    for slot, creatives in cached_payload.items()
                }
                if current_version and current_version == cached_version:
                    return AdConfigResponseSchema(version=cached_version, slots={})
                return AdConfigResponseSchema(version=cached_version, slots=payload)

        version, next_change = await self._determine_version(normalized_slots)
        if version == 0:
            payload = {slot: [] for slot in normalized_slots}
            _CONFIG_CACHE[cache_key] = (
                now_epoch,
                version,
                {slot: [] for slot in normalized_slots},
                next_change,
            )
            if current_version and current_version == version:
                return AdConfigResponseSchema(version=version, slots={})
            return AdConfigResponseSchema(version=version, slots=payload)

        data = await self._load_active_creatives(normalized_slots, platform)
        payload = {
            slot: [
                AdConfigCreativeSchema(
                    creative_id=item["creative_id"],
                    title=item["title"],
                    image_url=item["image_url"],
                    jump_type=item["jump_type"],
                    jump_payload=item["jump_payload"],
                    tags=item["tags"],
                    priority=item["priority"],
                    sort_order=item["sort_order"],
                )
                for item in data.get(slot, [])
            ]
            for slot in normalized_slots
        }

        _CONFIG_CACHE[cache_key] = (
            now_epoch,
            version,
            {slot: [item for item in data.get(slot, [])] for slot in normalized_slots},
            next_change,
        )

        if current_version and current_version == version:
            return AdConfigResponseSchema(version=version, slots={})
        return AdConfigResponseSchema(version=version, slots=payload)

    async def list_slots(self) -> list[AdSlot]:
        result = await self._session.execute(select(AdSlot).order_by(AdSlot.code))
        return list(result.scalars().all())

    async def create_slot(self, payload: AdSlotCreateSchema) -> AdSlot:
        exists_stmt = select(AdSlot).where(AdSlot.code == payload.code)
        exists = await self._session.execute(exists_stmt)
        if exists.scalar_one_or_none() is not None:
            raise AdvertisementServiceError("广告位编码已存在。")

        slot = AdSlot(
            code=payload.code.strip(),
            name=payload.name.strip(),
            description=payload.description,
            spec=payload.spec or {},
        )
        self._session.add(slot)
        await self._session.flush()
        await self._session.refresh(slot)
        self._invalidate_cache()
        return slot

    async def update_slot(self, code: str, payload: AdSlotUpdateSchema) -> AdSlot:
        slot = await self._session.execute(select(AdSlot).where(AdSlot.code == code))
        target = slot.scalar_one_or_none()
        if target is None:
            raise AdSlotNotFoundError("广告位不存在。")

        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            target.name = changes["name"]
        if "description" in changes:
            target.description = changes["description"]
        if "spec" in changes:
            target.spec = changes["spec"] or {}

        await self._session.flush()
        await self._session.refresh(target)
        self._invalidate_cache()
        return target

    async def create_creative(self, payload: AdCreativeCreateSchema) -> AdCreative:
        creative = AdCreative(
            title=payload.title,
            image_url=payload.image_url,
            jump_type=payload.jump_type,
            jump_payload=payload.jump_payload,
            start_time=payload.start_time,
            end_time=payload.end_time,
            enabled=payload.enabled,
            priority=payload.priority,
            platforms=payload.platforms or ["miniapp"],
            tags=payload.tags or [],
        )
        self._session.add(creative)
        await self._session.flush()
        await self._session.refresh(creative)
        self._invalidate_cache()
        return creative

    async def update_creative(
        self,
        creative_id: int,
        payload: AdCreativeUpdateSchema,
    ) -> AdCreative:
        creative = await self._session.get(AdCreative, creative_id)
        if creative is None:
            raise AdCreativeNotFoundError("素材不存在。")

        changes = payload.model_dump(exclude_unset=True)
        for field in (
            "title",
            "image_url",
            "jump_type",
            "jump_payload",
            "start_time",
            "end_time",
            "enabled",
            "priority",
        ):
            if field in changes:
                setattr(creative, field, changes[field])

        if "platforms" in changes:
            creative.platforms = changes["platforms"] or ["miniapp"]
        if "tags" in changes:
            creative.tags = changes["tags"] or []

        await self._session.flush()
        await self._session.refresh(creative)
        self._invalidate_cache()
        return creative

    async def delete_creative(self, creative_id: int) -> None:
        creative = await self._session.get(AdCreative, creative_id)
        if creative is None:
            raise AdCreativeNotFoundError("素材不存在。")
        await self._session.delete(creative)
        await self._session.flush()
        self._invalidate_cache()

    async def list_creatives(
        self,
        *,
        enabled: bool | None = None,
        platform: str | None = None,
    ) -> list[AdCreative]:
        stmt = select(AdCreative).order_by(AdCreative.priority, AdCreative.creative_id)
        if enabled is not None:
            stmt = stmt.where(AdCreative.enabled.is_(enabled))
        result = await self._session.execute(stmt)
        creatives = list(result.scalars().all())
        if platform is None:
            return creatives
        filtered: list[AdCreative] = []
        for creative in creatives:
            platforms = creative.platforms or ["miniapp"]
            if platform in platforms:
                filtered.append(creative)
        return filtered

    async def add_placement(self, payload: AdPlacementCreateSchema) -> AdPlacement:
        slot = await self._session.execute(select(AdSlot).where(AdSlot.code == payload.slot_code))
        if slot.scalar_one_or_none() is None:
            raise AdSlotNotFoundError("广告位不存在。")
        creative = await self._session.get(AdCreative, payload.creative_id)
        if creative is None:
            raise AdCreativeNotFoundError("素材不存在。")

        existing_stmt = select(AdPlacement).where(
            AdPlacement.slot_code == payload.slot_code,
            AdPlacement.creative_id == payload.creative_id,
        )
        exists = await self._session.execute(existing_stmt)
        if exists.scalar_one_or_none() is not None:
            raise AdPlacementConflictError("素材已投放至该广告位。")

        sort_order = payload.sort_order
        if sort_order is None:
            sort_stmt = select(func.max(AdPlacement.sort_order)).where(
                AdPlacement.slot_code == payload.slot_code
            )
            max_order = await self._session.execute(sort_stmt)
            current = max_order.scalar_one_or_none()
            sort_order = (current or 0) + 1

        placement = AdPlacement(
            slot_code=payload.slot_code,
            creative_id=payload.creative_id,
            sort_order=sort_order,
        )
        self._session.add(placement)
        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - 防御性处理
            raise AdPlacementConflictError("素材已投放至该广告位。") from exc

        await self._session.refresh(placement)
        self._invalidate_cache()
        return placement

    async def remove_placement(self, placement_id: int) -> None:
        placement = await self._session.get(AdPlacement, placement_id)
        if placement is None:
            raise AdPlacementNotFoundError("投放记录不存在。")
        await self._session.delete(placement)
        await self._session.flush()
        self._invalidate_cache()

    async def list_placements(self, slot_code: str) -> list[AdPlacement]:
        stmt: Select[tuple[AdPlacement]] = (
            select(AdPlacement)
            .options(selectinload(AdPlacement.creative))
            .where(AdPlacement.slot_code == slot_code)
            .order_by(AdPlacement.sort_order, AdPlacement.placement_id)
        )
        result = await self._session.execute(stmt)
        placements = list(result.scalars().all())
        if not placements:
            slot_exists = await self._session.execute(
                select(AdSlot.code).where(AdSlot.code == slot_code)
            )
            if slot_exists.scalar_one_or_none() is None:
                raise AdSlotNotFoundError("广告位不存在。")
        return placements

    async def update_placement_order(self, payload: AdPlacementOrderUpdateSchema) -> None:
        placements = await self._session.execute(
            select(AdPlacement)
            .where(AdPlacement.slot_code == payload.slot_code)
            .order_by(AdPlacement.sort_order, AdPlacement.placement_id)
        )
        placement_map = {
            placement.creative_id: placement for placement in placements.scalars().all()
        }
        missing = [
            creative_id for creative_id in payload.creative_ids if creative_id not in placement_map
        ]
        if missing:
            raise AdPlacementNotFoundError("部分素材未投放至该广告位, 无法排序。")

        for order, creative_id in enumerate(payload.creative_ids):
            placement = placement_map.get(creative_id)
            if placement is not None:
                placement.sort_order = order

        await self._session.flush()
        self._invalidate_cache()

    async def track_expose(
        self,
        *,
        slot_code: str,
        creative_id: int,
        user_id: int | None,
        session_id: str | None,
    ) -> None:
        logger.info(
            "advertisement.expose",
            slot_code=slot_code,
            creative_id=creative_id,
            user_id=user_id,
            session_id=session_id,
        )

    async def track_click(
        self,
        *,
        slot_code: str,
        creative_id: int,
        user_id: int | None,
        session_id: str | None,
    ) -> None:
        logger.info(
            "advertisement.click",
            slot_code=slot_code,
            creative_id=creative_id,
            user_id=user_id,
            session_id=session_id,
        )

    async def _determine_version(self, slots: Sequence[str]) -> tuple[int, datetime | None]:
        # 选用素材、投放、广告位的最新更新时间戳作为版本号
        creative_ts = await self._session.execute(select(func.max(AdCreative.updated_at)))
        placement_ts = await self._session.execute(select(func.max(AdPlacement.updated_at)))
        slot_ts = await self._session.execute(select(func.max(AdSlot.created_at)))

        timestamps = [
            creative_ts.scalar_one_or_none(),
            placement_ts.scalar_one_or_none(),
            slot_ts.scalar_one_or_none(),
        ]
        timestamps = [value for value in timestamps if value is not None]
        now = datetime.now(tz=UTC)

        if slots:
            start_past = await self._session.execute(
                select(func.max(AdCreative.start_time))
                .join(AdPlacement, AdPlacement.creative_id == AdCreative.creative_id)
                .where(AdPlacement.slot_code.in_(slots))
                .where(AdCreative.start_time.is_not(None))
                .where(AdCreative.start_time <= now)
            )
            end_past = await self._session.execute(
                select(func.max(AdCreative.end_time))
                .join(AdPlacement, AdPlacement.creative_id == AdCreative.creative_id)
                .where(AdPlacement.slot_code.in_(slots))
                .where(AdCreative.end_time.is_not(None))
                .where(AdCreative.end_time <= now)
            )
            past_candidates = [start_past.scalar_one_or_none(), end_past.scalar_one_or_none()]
            timestamps.extend([value for value in past_candidates if value is not None])

        latest_ts = None
        if timestamps:
            latest_ts = max(timestamps)
            if latest_ts.tzinfo is None:
                latest_ts = latest_ts.replace(tzinfo=UTC)

        next_change: datetime | None = None
        if slots:
            start_future = await self._session.execute(
                select(func.min(AdCreative.start_time))
                .join(AdPlacement, AdPlacement.creative_id == AdCreative.creative_id)
                .where(AdPlacement.slot_code.in_(slots))
                .where(AdCreative.start_time.is_not(None))
                .where(AdCreative.start_time > now)
            )
            end_future = await self._session.execute(
                select(func.min(AdCreative.end_time))
                .join(AdPlacement, AdPlacement.creative_id == AdCreative.creative_id)
                .where(AdPlacement.slot_code.in_(slots))
                .where(AdCreative.end_time.is_not(None))
                .where(AdCreative.end_time > now)
            )
            future_candidates = [
                start_future.scalar_one_or_none(),
                end_future.scalar_one_or_none(),
            ]
            future_candidates = [value for value in future_candidates if value is not None]
            if future_candidates:
                next_change = min(future_candidates)
                if next_change.tzinfo is None:
                    next_change = next_change.replace(tzinfo=UTC)

        version = 0
        if latest_ts is not None:
            version = int(latest_ts.timestamp())
        return version, next_change

    async def _load_active_creatives(
        self,
        slots: Sequence[str],
        platform: str,
    ) -> dict[str, list[dict[str, Any]]]:
        stmt: Select[tuple[AdPlacement, AdCreative]] = (
            select(AdPlacement, AdCreative)
            .join(AdCreative, AdCreative.creative_id == AdPlacement.creative_id)
            .where(AdPlacement.slot_code.in_(slots))
        )
        result = await self._session.execute(stmt)
        records = result.all()
        now = datetime.now(tz=UTC)

        payload: dict[str, list[dict[str, Any]]] = {slot: [] for slot in slots}
        for placement, creative in records:
            if not creative.enabled:
                continue
            if creative.start_time and creative.start_time > now:
                continue
            if creative.end_time and creative.end_time < now:
                continue
            platforms = creative.platforms or ["miniapp"]
            if platform not in platforms:
                continue

            payload.setdefault(placement.slot_code, []).append(
                {
                    "creative_id": creative.creative_id,
                    "title": creative.title,
                    "image_url": creative.image_url,
                    "jump_type": creative.jump_type,
                    "jump_payload": creative.jump_payload,
                    "tags": list(creative.tags or []),
                    "priority": int(creative.priority or 0),
                    "sort_order": placement.sort_order,
                }
            )

        for slot in payload:
            payload[slot].sort(
                key=lambda item: (
                    item["priority"],
                    item["sort_order"],
                    item["creative_id"],
                )
            )
        return payload

    @staticmethod
    def _build_cache_key(slots: Sequence[str], platform: str) -> str:
        return f"{platform}:{','.join(slots)}"

    @staticmethod
    def _invalidate_cache() -> None:
        if _CONFIG_CACHE:
            _CONFIG_CACHE.clear()
