from __future__ import annotations

import pytest
from app.db.session import get_async_session
from app.main import app
from app.models.shop import ShopProfile
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_shop_status_returns_profile(db_session) -> None:
    profile = ShopProfile(
        id=1,
        is_open=False,
        open_hours_json=[{"weekday": 1, "ranges": [["09:00", "21:00"]]}],
        location_lat=31.2304,
        location_lng=121.4737,
        delivery_radius_m=1200,
        timezone="Asia/Shanghai",
    )
    db_session.add(profile)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/shop/status")
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_open"] is False
    assert payload["delivery_radius_m"] == 1200
    assert payload["location"] == {"lat": 31.2304, "lng": 121.4737}
    assert payload["features"]["multi_category_enabled"] is True


@pytest.mark.asyncio
async def test_delivery_check_within_radius(db_session) -> None:
    profile = ShopProfile(
        id=1,
        location_lat=31.2304,
        location_lng=121.4737,
        delivery_radius_m=1200,
        timezone="Asia/Shanghai",
    )
    db_session.add(profile)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/shop/delivery/check",
                json={"lat": 31.2304, "lng": 121.4737},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    result = response.json()
    assert result["deliverable"] is True
    assert result["distance_m"] == 0.0


@pytest.mark.asyncio
async def test_delivery_check_outside_radius(db_session) -> None:
    profile = ShopProfile(
        id=1,
        location_lat=31.2304,
        location_lng=121.4737,
        delivery_radius_m=500,
        timezone="Asia/Shanghai",
    )
    db_session.add(profile)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/shop/delivery/check",
                json={"lat": 31.2404, "lng": 121.4737},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    result = response.json()
    assert result["deliverable"] is False
    assert result["distance_m"] > 500


@pytest.mark.asyncio
async def test_delivery_check_without_location(db_session) -> None:
    profile = ShopProfile(id=1, delivery_radius_m=1000)
    db_session.add(profile)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/shop/delivery/check",
                json={"lat": 31.2304, "lng": 121.4737},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Shop location not configured."
