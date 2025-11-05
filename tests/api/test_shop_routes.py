from __future__ import annotations

import json

import pytest
from app.api.routes.shop import get_shop_service
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.shop import ShopProfile
from app.services.shop import ShopService
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_shop_profile_returns_snapshot(db_session, tmp_path) -> None:
    snapshot = {
        "name": "奈茶王府井店",
        "address": "北京市东城区王府井大街1号",
        "phone": "010-66668888",
        "announcement": "双十一全场 8 折！",
        "logo_url": "https://cdn.example.com/logo.png",
        "updated_at": "2025-10-15T08:00:00+08:00",
    }
    profile_file = tmp_path / "shop_profile.json"
    profile_file.write_text(json.dumps(snapshot), encoding="utf-8")

    base_settings = get_settings()
    test_settings = base_settings.model_copy(update={"shop_profile_file": str(profile_file)})

    async def override_get_shop_service() -> ShopService:
        return ShopService(db_session, test_settings)

    app.dependency_overrides[get_async_session] = lambda: db_session
    app.dependency_overrides[get_shop_service] = override_get_shop_service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/shop/profile")
    finally:
        app.dependency_overrides.pop(get_shop_service, None)
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == snapshot["name"]
    assert payload["announcement"] == snapshot["announcement"]
    assert payload["address"] == snapshot["address"]
    assert payload["phone"] == snapshot["phone"]
    assert payload["logo_url"] == snapshot["logo_url"]
    assert payload["updated_at"] == snapshot["updated_at"]


@pytest.mark.asyncio
async def test_shop_profile_reads_from_redis(db_session, monkeypatch) -> None:
    snapshot = {
        "name": "奈茶徐家汇店",
        "address": "上海市徐汇区肇嘉浜路100号",
        "phone": "021-55556666",
        "announcement": "门店升级装修，敬请期待！",
        "logo_url": "https://cdn.example.com/logo-xjh.png",
        "updated_at": "2025-10-16T09:00:00+08:00",
    }

    class DummyRedisClient:
        def __init__(self, value: str):
            self._value = value

        async def get(self, key: str) -> str:
            return self._value

    redis_payload = json.dumps(snapshot, ensure_ascii=False)
    dummy_client = DummyRedisClient(redis_payload)

    monkeypatch.setattr("app.services.shop._SHOP_PROFILE_CLIENT", None, raising=False)
    monkeypatch.setattr(
        "app.services.shop.ShopService._get_profile_cache_client",
        lambda self: dummy_client,
    )

    base_settings = get_settings()
    test_settings = base_settings.model_copy(
        update={
            "shop_profile_cache_url": "redis://localhost:6379/9",
            "shop_profile_file": "app/data/non_existent.json",
        }
    )

    async def override_get_shop_service() -> ShopService:
        return ShopService(db_session, test_settings)

    app.dependency_overrides[get_async_session] = lambda: db_session
    app.dependency_overrides[get_shop_service] = override_get_shop_service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/shop/profile")
    finally:
        app.dependency_overrides.pop(get_shop_service, None)
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == snapshot["name"]
    assert payload["announcement"] == snapshot["announcement"]
    assert payload["address"] == snapshot["address"]
    assert payload["phone"] == snapshot["phone"]
    assert payload["logo_url"] == snapshot["logo_url"]
    assert payload["updated_at"] == snapshot["updated_at"]


@pytest.mark.asyncio
async def test_shop_profile_missing_snapshot(db_session, tmp_path) -> None:
    profile_file = tmp_path / "shop_profile.json"

    base_settings = get_settings()
    test_settings = base_settings.model_copy(update={"shop_profile_file": str(profile_file)})

    async def override_get_shop_service() -> ShopService:
        return ShopService(db_session, test_settings)

    app.dependency_overrides[get_async_session] = lambda: db_session
    app.dependency_overrides[get_shop_service] = override_get_shop_service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/shop/profile")
    finally:
        app.dependency_overrides.pop(get_shop_service, None)
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Shop profile snapshot 不存在。"


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


@pytest.mark.asyncio
async def test_delivery_check_respects_buffer(db_session) -> None:
    profile = ShopProfile(
        id=1,
        location_lat=31.2304,
        location_lng=121.4737,
        delivery_radius_m=0,
    )
    db_session.add(profile)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/shop/delivery/check",
                json={"lat": 31.2304 + 0.00015, "lng": 121.4737},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    result = response.json()
    assert result["deliverable"] is True
    assert result["distance_m"] > 0


@pytest.mark.asyncio
async def test_delivery_check_invalid_coordinates(db_session) -> None:
    profile = ShopProfile(
        id=1,
        location_lat=31.2304,
        location_lng=121.4737,
        delivery_radius_m=500,
    )
    db_session.add(profile)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/shop/delivery/check",
                json={"lat": 123.456, "lng": 10},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 422
