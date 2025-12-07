from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_async_session
from app.main import app


@pytest.mark.asyncio
async def test_want_route_missing_product_returns_404(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response_want = await client.post("/api/v1/products/123/want")
            assert response_want.status_code == 404
    finally:
        app.dependency_overrides.pop(get_async_session, None)
