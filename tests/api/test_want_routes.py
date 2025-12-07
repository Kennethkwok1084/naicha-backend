from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import TokenScope, create_access_token
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin, User
from app.models.catalog import Category, Product
from app.models.orders import WantEvent


async def _seed_product(db_session) -> Product:
    category = Category(category_id=6001, name="想要 API", sort_order=1)
    product = Product(
        product_id=6001,
        category_id=category.category_id,
        name="想要测试饮品",
        description="",
        base_price=Decimal("13.50"),
        status="active",
        inventory_status="sold_out",
        stock_quantity=0,
    )
    db_session.add_all([category, product])
    await db_session.flush()
    return product


def _user_token(user_id: int) -> str:
    return create_access_token(subject=str(user_id), scope=TokenScope.USER)


@pytest.mark.asyncio
async def test_guest_want_submission(db_session) -> None:
    product = await _seed_product(db_session)
    settings = get_settings()
    original = settings.want_enabled
    settings.want_enabled = True

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/products/{product.product_id}/want")
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["product_id"] == product.product_id
            assert payload["source"] == "guest"

        events = await db_session.execute(
            select(WantEvent).where(WantEvent.product_id == product.product_id)
        )
        assert len(list(events.scalars())) == 1
    finally:
        settings.want_enabled = original
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_user_want_rate_limited(db_session) -> None:
    product = await _seed_product(db_session)
    user = User(user_id=7001, open_id="want-api-user")
    db_session.add(user)
    await db_session.flush()

    settings = get_settings()
    original = settings.want_enabled
    settings.want_enabled = True

    token = _user_token(user.user_id)
    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                f"/api/v1/products/{product.product_id}/want",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert first.status_code == 200

            second = await client.post(
                f"/api/v1/products/{product.product_id}/want",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert second.status_code == 429
    finally:
        settings.want_enabled = original
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_want_feature_disabled_returns_503(db_session) -> None:
    product = await _seed_product(db_session)
    settings = get_settings()
    original = settings.want_enabled
    settings.want_enabled = False

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v1/products/{product.product_id}/want")
            assert response.status_code == 503
    finally:
        settings.want_enabled = original
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_admin_want_stats(db_session) -> None:
    product = await _seed_product(db_session)
    admin = Admin(admin_id=9001, username="want-admin", password_hash="x", role="admin")
    db_session.add(admin)
    await db_session.flush()

    settings = get_settings()
    original_flag = settings.want_enabled
    settings.want_enabled = True

    service_time = datetime.now(tz=UTC) - timedelta(days=1)
    event = WantEvent(
        product_id=product.product_id,
        user_id=None,
        ip_hash="hash",
        user_agent=None,
        created_at=service_time,
    )
    db_session.add(event)
    await db_session.flush()

    token = create_access_token(subject=str(admin.admin_id), scope=TokenScope.ADMIN)
    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/want/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["top_products"]
            assert payload["top_products"][0]["product_id"] == product.product_id
    finally:
        settings.want_enabled = original_flag
        app.dependency_overrides.pop(get_async_session, None)
