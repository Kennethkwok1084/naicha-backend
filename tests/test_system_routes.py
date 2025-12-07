import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import system as system_routes
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app


def test_get_app_settings_returns_cached_settings() -> None:
    settings = system_routes.get_app_settings()
    assert settings.app_env in {"dev", "staging", "prod"}


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_liveness_endpoint_returns_live() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


@pytest.mark.asyncio
async def test_readiness_endpoint_checks_database(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz/ready")
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_metrics_endpoint_respects_toggle() -> None:
    override_settings = get_settings().model_copy(update={"prometheus_enabled": False})
    app.dependency_overrides[system_routes.get_app_settings] = lambda: override_settings

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")
    finally:
        app.dependency_overrides.pop(system_routes.get_app_settings, None)

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Prometheus metrics endpoint is disabled."


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_payload() -> None:
    app.dependency_overrides[system_routes.get_app_settings] = lambda: get_settings()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")
    finally:
        app.dependency_overrides.pop(system_routes.get_app_settings, None)

    assert response.status_code == 200
    assert response.headers.get("Content-Type", "").startswith("text/plain")
    assert len(response.text) > 0
