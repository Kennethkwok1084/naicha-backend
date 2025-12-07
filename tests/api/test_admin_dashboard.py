from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import TokenScope, create_access_token
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin, User
from app.models.orders import Order, OrderItem
from app.services.dashboard import DashboardService


def _admin_token(admin_id: int) -> str:
    return create_access_token(subject=str(admin_id), scope=TokenScope.ADMIN)


def _fixed_now() -> datetime:
    return datetime(2025, 10, 21, 10, 0, 0, tzinfo=UTC)


async def _seed_orders(session, *, now: datetime) -> None:
    admin = Admin(admin_id=900, username="dashboard-admin", password_hash="x", role="admin")
    user = User(user_id=910, open_id="dashboard-user")
    session.add_all([admin, user])
    await session.flush()

    # within range orders
    order1 = Order(
        order_id=920,
        order_number="DASH-920",
        total_price=Decimal("30.00"),
        status="paid",
        payment_status="paid",
        payment_channel="wechat_jsapi",
        order_type="pickup",
        user_id=user.user_id,
    )
    order1.created_at = now - timedelta(hours=2)
    order1.updated_at = now - timedelta(hours=2)

    order2 = Order(
        order_id=921,
        order_number="DASH-921",
        total_price=Decimal("20.00"),
        status="refunded",
        payment_status="paid",
        payment_channel="static_qr",
        order_type="pickup",
        user_id=user.user_id,
    )
    order2.created_at = now - timedelta(hours=1)
    order2.updated_at = now - timedelta(hours=1)

    order3_prev = Order(
        order_id=922,
        order_number="DASH-922",
        total_price=Decimal("15.00"),
        status="paid",
        payment_status="paid",
        payment_channel="cash",
        order_type="pickup",
        user_id=user.user_id,
    )
    order3_prev.created_at = now - timedelta(days=1, hours=2)
    order3_prev.updated_at = now - timedelta(days=1, hours=2)

    session.add_all([order1, order2, order3_prev])
    await session.flush()

    session.add_all(
        [
            OrderItem(
                item_id=930,
                order_id=order1.order_id,
                product_id=1,
                product_name="红茶拿铁",
                quantity=2,
                unit_price=Decimal("15.00"),
            ),
            OrderItem(
                item_id=931,
                order_id=order2.order_id,
                product_id=2,
                product_name="乌龙奶盖",
                quantity=1,
                unit_price=Decimal("20.00"),
            ),
        ]
    )
    await session.flush()


@pytest.mark.asyncio
async def test_dashboard_day_range_with_compare(db_session, monkeypatch) -> None:
    now = _fixed_now()
    await _seed_orders(db_session, now=now)

    # ensure cache clean and deterministic now
    service = DashboardService(db_session, get_settings())
    await service.invalidate_cache()
    monkeypatch.setattr(DashboardService, "_now", staticmethod(lambda: now))  # type: ignore[attr-defined]

    token = _admin_token(900)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/dashboard",
                headers={"Authorization": f"Bearer {token}"},
                params={"range": "day", "compare": "true"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["range"] == "day"
    summary = payload["summary"]
    assert summary["order_count"] == 2
    assert summary["gross_sales"] == 50.0
    assert summary["refund_amount"] == 20.0
    assert payload["compare_summary"]["order_count"] == 1
    assert any(point["order_count"] > 0 for point in payload["trend"])
    assert payload["top_products"][0]["product_id"] == 1
    channels = {item["channel"]: item["order_count"] for item in payload["payment_channel_split"]}
    assert channels["wechat_jsapi"] == 1
    assert channels["static_qr"] == 1


@pytest.mark.asyncio
async def test_dashboard_invalid_range_returns_422(db_session) -> None:
    service = DashboardService(db_session, get_settings())
    await service.invalidate_cache()

    admin = Admin(admin_id=901, username="dash-invalid", password_hash="x", role="admin")
    db_session.add(admin)
    await db_session.flush()

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/dashboard",
                headers={"Authorization": f"Bearer {token}"},
                params={"range": "quarter"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 422
