from __future__ import annotations

import pytest
from app.core.settings import get_settings
from app.models.shop import ShopProfile
from app.services.shop import ShopProfileNotConfiguredError, ShopService


@pytest.mark.asyncio
async def test_get_profile_autocreates_default_record(db_session) -> None:
    settings = get_settings().model_copy(update={"delivery_radius_m": 800})
    service = ShopService(db_session, settings)

    profile = await service.get_profile()
    assert profile.id == 1
    assert profile.delivery_radius_m is None  # 使用全局默认

    profile.is_open = False
    await db_session.flush()

    status_payload = await service.get_status_payload()
    assert status_payload["delivery_radius_m"] == 800
    assert status_payload["features"]["multi_category_enabled"] == settings.multi_category_enabled


@pytest.mark.asyncio
async def test_check_delivery_requires_coordinates(db_session) -> None:
    settings = get_settings().model_copy()
    service = ShopService(db_session, settings)

    profile = ShopProfile(id=1, is_open=True, delivery_radius_m=500)
    db_session.add(profile)
    await db_session.flush()

    with pytest.raises(ShopProfileNotConfiguredError):
        await service.check_delivery(lat=0.0, lng=0.0)


@pytest.mark.asyncio
async def test_check_delivery_uses_haversine_and_buffer(db_session) -> None:
    settings = get_settings().model_copy(update={"delivery_radius_m": 100})
    service = ShopService(db_session, settings)

    profile = ShopProfile(
        id=1,
        location_lat=31.2304,
        location_lng=121.4737,
        delivery_radius_m=100,
    )
    db_session.add(profile)
    await db_session.flush()

    deliverable, distance = await service.check_delivery(31.2304, 121.4737)
    assert deliverable is True
    assert distance == 0.0

    deliverable_far, distance_far = await service.check_delivery(31.2315, 121.4737)
    assert deliverable_far is False or distance_far > 120
