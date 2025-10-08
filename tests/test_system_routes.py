import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import system as system_routes
from app.core.settings import get_settings
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
