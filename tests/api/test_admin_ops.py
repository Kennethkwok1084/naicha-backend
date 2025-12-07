from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin
from app.models.catalog import Product
from app.models.orders import Order, OrderItem


def _admin_token(admin_id: int) -> str:
    return create_access_token(subject=str(admin_id), scope=TokenScope.ADMIN)


@pytest.mark.asyncio
async def test_ops_auto_cancel_endpoint_cancels_orders(db_session) -> None:
    admin = Admin(admin_id=8801, username="ops-admin", password_hash="x", role="admin")
    product = Product(
        product_id=881,
        name="秋季限定奶茶",
        base_price=Decimal("18.00"),
        status="active",
        inventory_status="sold_out",
        stock_quantity=0,
    )
    created_at = datetime.now(tz=UTC) - timedelta(minutes=90)
    order = Order(
        order_id=7701,
        order_number="OPS-ORDER-01",
        user_id=None,
        total_price=Decimal("18.00"),
        notes=None,
        status="pending_payment",
        payment_status="pending",
        order_type="pickup",
        source="user",
        payment_channel=None,
        created_at=created_at,
        updated_at=created_at,
    )
    item = OrderItem(
        item_id=9901,
        order_id=order.order_id,
        product_id=product.product_id,
        product_name=product.name,
        quantity=1,
        unit_price=Decimal("18.00"),
        selected_specs_json=None,
    )
    db_session.add_all([admin, product, order, item])
    await db_session.flush()

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ops/orders/auto-cancel",
                headers={"Authorization": f"Bearer {token}"},
                json={"cutoff_minutes": 30, "limit": 10},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["count"] == 1
    assert payload["cancelled_order_ids"] == [order.order_id]
    assert payload["source"] == "http"

    await db_session.refresh(order)
    await db_session.refresh(product)
    assert order.status == "cancelled"
    assert order.payment_status == "pending"
    assert product.stock_quantity == 1
    assert product.inventory_status == "in_stock"


@pytest.mark.asyncio
async def test_ops_auto_cancel_requires_privileged_role(db_session) -> None:
    clerk = Admin(admin_id=8802, username="ops-clerk", password_hash="x", role="clerk")
    db_session.add(clerk)
    await db_session.flush()

    token = _admin_token(clerk.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ops/orders/auto-cancel",
                headers={"Authorization": f"Bearer {token}"},
                json={"cutoff_minutes": 30},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 403, response.json()
