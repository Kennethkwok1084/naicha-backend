from __future__ import annotations

import json

import pytest
from app.api.routes.config import get_config_service
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin
from app.models.shop import ShopConfig
from app.services.config import ConfigService
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_public_config_merges_feature_flags(db_session, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "app_config.json"
    config_payload = {
        "version": "1.0.0",
        "ttl_seconds": 120,
        "contact": {"phone": "13800001234", "business_hours": "09:00-21:00"},
        "legal": {"privacy_url": "https://example.com/privacy"},
        "ui": {"eta_fallback_text": "制作中，请稍后"},
        "assets": {"cdn_base_url": None},
        "features": {
            "disable_delivery": False,
            "disable_coupons": False,
            "disable_stamps": False,
        },
    }
    config_file.write_text(json.dumps(config_payload), encoding="utf-8")

    db_session.add(
        ShopConfig(
            config_key="features.disable_delivery",
            value_json=True,
            category="features",
            description="天气原因",
        )
    )
    await db_session.commit()

    base_settings = get_settings()
    test_settings = base_settings.model_copy(
        update={
            "public_config_file": str(config_file),
            "public_config_cache_key": "test:public_config",
            "public_config_cache_ttl_seconds": 60,
        }
    )

    monkeypatch.setattr("app.services.config._CONFIG_CACHE_CLIENT", None, raising=False)
    monkeypatch.setattr("app.services.config.ConfigService._get_cache_client", lambda self: None)

    async def override_get_config_service() -> ConfigService:
        return ConfigService(db_session, test_settings)

    app.dependency_overrides[get_async_session] = lambda: db_session
    app.dependency_overrides[get_config_service] = override_get_config_service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/config")
    finally:
        app.dependency_overrides.pop(get_async_session, None)
        app.dependency_overrides.pop(get_config_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "1.0.0"
    assert payload["features"]["disable_delivery"] is True
    assert payload["features"]["disable_coupons"] is False
    assert payload["features"]["disable_stamps"] is False
    assert payload["contact"]["phone"] == "13800001234"
    assert payload["ttl_seconds"] == 120


@pytest.mark.asyncio
async def test_admin_update_feature_toggle_updates_cache_and_db(
    db_session, tmp_path, monkeypatch
) -> None:
    admin = Admin(admin_id=1, username="admin", password_hash="hashed", role="admin")
    db_session.add(admin)
    await db_session.commit()

    config_file = tmp_path / "app_config.json"
    config_file.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "ttl_seconds": 120,
                "contact": {"phone": "13800001234", "business_hours": "09:00-21:00"},
                "legal": {"privacy_url": "https://example.com/privacy"},
                "ui": {"eta_fallback_text": "制作中，请稍后"},
                "assets": {"cdn_base_url": None},
                "features": {
                    "disable_delivery": False,
                    "disable_coupons": False,
                    "disable_stamps": False,
                },
            }
        ),
        encoding="utf-8",
    )

    base_settings = get_settings()
    test_settings = base_settings.model_copy(
        update={
            "public_config_file": str(config_file),
            "public_config_cache_key": "test:public_config",
            "public_config_cache_ttl_seconds": 60,
        }
    )

    class DummyCache:
        def __init__(self) -> None:
            self.deleted_keys: list[str] = []

        async def get(self, _key: str) -> None:
            return None

        async def setex(self, _key: str, _ttl: int, _value: str) -> bool:
            return True

        async def delete(self, key: str) -> int:
            self.deleted_keys.append(key)
            return 1

    dummy_cache = DummyCache()
    monkeypatch.setattr("app.services.config._CONFIG_CACHE_CLIENT", None, raising=False)
    monkeypatch.setattr(
        "app.services.config.ConfigService._get_cache_client",
        lambda self: dummy_cache,
    )

    async def override_get_config_service() -> ConfigService:
        return ConfigService(db_session, test_settings)

    app.dependency_overrides[get_async_session] = lambda: db_session
    app.dependency_overrides[get_config_service] = override_get_config_service
    from app.api.dependencies.auth import get_current_admin

    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/admin/config/features/disable_coupons",
                json={"enabled": True, "reason": "活动暂停"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)
        app.dependency_overrides.pop(get_config_service, None)
        app.dependency_overrides.pop(get_current_admin, None)

    assert response.status_code == 200
    body = response.json()
    assert body["config_key"] == "features.disable_coupons"
    assert body["value"] is True
    assert body["updated_by_admin_id"] == 1
    assert dummy_cache.deleted_keys == ["test:public_config"]

    record = await db_session.get(ShopConfig, "features.disable_coupons")
    assert record is not None
    assert record.value_json is True
