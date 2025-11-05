from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.models.advertisement import AdCreative, AdPlacement, AdSlot
from app.schemas import AdCreativeUpdateSchema
from app.services.advertisement import AdvertisementService


@pytest.fixture(autouse=True)
def _clear_ad_config_cache():
    AdvertisementService._invalidate_cache()
    yield
    AdvertisementService._invalidate_cache()


async def _seed_basic_ad(db_session) -> tuple[AdSlot, AdCreative, AdPlacement]:
    slot = AdSlot(slot_id=5001, code="HOME_BANNER", name="首页轮播", spec={"max": 5})
    creative = AdCreative(
        creative_id=6001,
        title="新品上线",
        image_url="https://cdn.example.com/banner.png",
        jump_type="miniapp_page",
        jump_payload={"path": "/pages/menu/index"},
        enabled=True,
        priority=10,
        platforms=["miniapp"],
        tags=["launch"],
    )
    placement = AdPlacement(
        placement_id=7001,
        slot_code=slot.code,
        creative_id=creative.creative_id,
        sort_order=0,
    )
    db_session.add_all([slot, creative, placement])
    await db_session.flush()
    return slot, creative, placement


@pytest.mark.asyncio
async def test_get_config_basic_flow(db_session) -> None:
    await _seed_basic_ad(db_session)
    service = AdvertisementService(db_session)

    result = await service.get_config(slots=["HOME_BANNER"], platform="miniapp")
    assert result.version > 0
    assert "HOME_BANNER" in result.slots
    assert len(result.slots["HOME_BANNER"]) == 1
    assert result.slots["HOME_BANNER"][0].creative_id == 6001

    cached = await service.get_config(
        slots=["HOME_BANNER"],
        platform="miniapp",
        current_version=result.version,
    )
    assert cached.version == result.version
    assert cached.slots == {}


@pytest.mark.asyncio
async def test_get_config_filters_by_platform_and_time(db_session) -> None:
    slot, creative, _ = await _seed_basic_ad(db_session)
    future_creative = AdCreative(
        creative_id=6002,
        title="定时上线",
        image_url="https://cdn.example.com/future.png",
        jump_type="miniapp_page",
        start_time=datetime.now(tz=UTC) + timedelta(days=1),
        enabled=True,
        priority=5,
        platforms=["miniapp"],
    )
    merchant_creative = AdCreative(
        creative_id=6003,
        title="商家端展示",
        image_url="https://cdn.example.com/merchant.png",
        jump_type="miniapp_page",
        enabled=True,
        priority=1,
        platforms=["merchant"],
    )
    future_placement = AdPlacement(
        placement_id=7002,
        slot_code=slot.code,
        creative_id=future_creative.creative_id,
        sort_order=1,
    )
    merchant_placement = AdPlacement(
        placement_id=7003,
        slot_code=slot.code,
        creative_id=merchant_creative.creative_id,
        sort_order=2,
    )
    db_session.add_all([future_creative, merchant_creative, future_placement, merchant_placement])
    await db_session.flush()

    service = AdvertisementService(db_session)
    result = await service.get_config(slots=[slot.code], platform="miniapp")
    creative_ids = [item.creative_id for item in result.slots[slot.code]]
    assert creative.creative_id in creative_ids
    assert future_creative.creative_id not in creative_ids
    assert merchant_creative.creative_id not in creative_ids


@pytest.mark.asyncio
async def test_get_config_excludes_disabled_creatives(db_session) -> None:
    _, creative, placement = await _seed_basic_ad(db_session)
    creative.enabled = False
    await db_session.flush()

    service = AdvertisementService(db_session)
    result = await service.get_config(slots=[placement.slot_code], platform="miniapp")
    assert result.slots == {placement.slot_code: []}


@pytest.mark.asyncio
async def test_update_creative_invalidates_cache(db_session) -> None:
    _, creative, _ = await _seed_basic_ad(db_session)
    service = AdvertisementService(db_session)

    initial = await service.get_config(slots=["HOME_BANNER"], platform="miniapp")
    await service.update_creative(
        creative_id=creative.creative_id,
        payload=AdCreativeUpdateSchema(title="限时折扣"),
    )

    refreshed = await service.get_config(slots=["HOME_BANNER"], platform="miniapp")
    assert refreshed.version >= initial.version
    assert refreshed.slots["HOME_BANNER"][0].title == "限时折扣"


@pytest.mark.asyncio
async def test_version_changes_when_start_time_passed(monkeypatch, db_session) -> None:
    slot, creative, _ = await _seed_basic_ad(db_session)
    system_now = datetime.now(tz=UTC)
    go_live = system_now + timedelta(minutes=10)
    base_now = go_live - timedelta(minutes=1)
    creative.start_time = go_live
    await db_session.flush()

    service = AdvertisementService(db_session)

    monkeypatch.setattr(
        "app.services.advertisement.datetime",
        SimpleNamespace(now=lambda tz=None: base_now),
    )
    initial = await service.get_config(slots=[slot.code], platform="miniapp")
    first_version = initial.version
    assert initial.slots[slot.code] == []

    monkeypatch.setattr(
        "app.services.advertisement.datetime",
        SimpleNamespace(now=lambda tz=None: go_live + timedelta(seconds=1)),
    )
    refreshed = await service.get_config(
        slots=[slot.code],
        platform="miniapp",
        current_version=initial.version,
    )
    assert refreshed.version > first_version
    assert refreshed.slots[slot.code][0].creative_id == creative.creative_id
