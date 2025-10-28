from __future__ import annotations

import pytest
from app.db.session import get_async_session
from app.main import app
from app.models.advertisement import AdCreative, AdPlacement, AdSlot
from app.services.advertisement import AdvertisementService
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _clear_ad_cache() -> None:
    AdvertisementService._invalidate_cache()
    yield
    AdvertisementService._invalidate_cache()


async def _seed_basic_ad(db_session) -> tuple[AdSlot, AdCreative, AdPlacement]:
    slot = AdSlot(slot_id=8001, code="HOME_BANNER", name="首页轮播", spec={"max": 5})
    creative = AdCreative(
        creative_id=8101,
        title="冬季上新",
        image_url="https://cdn.example.com/winter.png",
        jump_type="miniapp_page",
        jump_payload={"path": "/pages/menu/index"},
        enabled=True,
        priority=5,
        platforms=["miniapp"],
    )
    placement = AdPlacement(
        placement_id=8201,
        slot_code=slot.code,
        creative_id=creative.creative_id,
        sort_order=0,
    )
    db_session.add_all([slot, creative, placement])
    await db_session.flush()
    return slot, creative, placement


@pytest.mark.asyncio
async def test_public_ads_config_and_tracking(db_session) -> None:
    slot, creative, _ = await _seed_basic_ad(db_session)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get(
                "/api/v1/ads/config",
                params={"slots": slot.code, "platform": "miniapp"},
            )
            assert first.status_code == 200
            body = first.json()
            assert body["version"] > 0
            assert slot.code in body["slots"]
            assert body["slots"][slot.code][0]["creative_id"] == creative.creative_id

            version = body["version"]
            cached = await client.get(
                "/api/v1/ads/config",
                params={"slots": slot.code, "platform": "miniapp", "ver": version},
            )
            assert cached.status_code == 200
            assert cached.json()["slots"] == {}

            expose = await client.post(
                "/api/v1/ads/track/expose",
                json={"slot": slot.code, "creative_id": creative.creative_id},
            )
            assert expose.status_code == 204

            click = await client.post(
                "/api/v1/ads/track/click",
                json={"slot": slot.code, "creative_id": creative.creative_id, "user_id": 123},
            )
            assert click.status_code == 204
    finally:
        app.dependency_overrides.pop(get_async_session, None)
