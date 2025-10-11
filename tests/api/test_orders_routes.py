from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.orders import IdempotencyKey


async def _seed_product(db_session) -> None:
    category = Category(category_id=101, name="特调", sort_order=1)
    product = Product(
        product_id=101,
        category_id=category.category_id,
        name="桂花乌龙",
        description="热卖",
        base_price=Decimal("15.00"),
        status="active",
        inventory_status="in_stock",
    )
    group = SpecGroup(group_id=101, name="加料", sort_order=1)
    option = SpecOption(
        option_id=101,
        group_id=group.group_id,
        name="珍珠",
        price_modifier=Decimal("2.00"),
        inventory_status="in_stock",
        sort_order=1,
    )
    mapping = ProductSpecMapping(
        mapping_id=101,
        product_id=product.product_id,
        group_id=group.group_id,
    )
    db_session.add_all([category, product, group, option, mapping])
    await db_session.flush()


@pytest.mark.asyncio
async def test_create_order_api_with_user_token(db_session) -> None:
    await _seed_product(db_session)
    user = User(user_id=200, open_id="user-token")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "idem-api-1",
                },
                json={
                    "items": [
                        {"product_id": 101, "quantity": 1, "spec_option_ids": [101]},
                    ],
                    "order_type": "pickup",
                    "notes": "无糖",
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["order_type"] == "pickup"
            assert payload["total_price"] == 17.0
            assert payload["items"][0]["product_id"] == 101

            order_id = payload["order_id"]

            jsapi_resp = await client.post(
                f"/api/v1/orders/{order_id}/pay/jsapi",
                headers={"Authorization": f"Bearer {token}"},
                json={"payer_open_id": "wx-user"},
            )
            assert jsapi_resp.status_code == 200
            assert jsapi_resp.json()["channel"] == "wechat_jsapi"

            native_resp = await client.post(
                f"/api/v1/orders/{order_id}/pay/native",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
            assert native_resp.status_code == 200
            assert native_resp.json()["channel"] == "wechat_native"

            # 再次使用相同幂等键应返回相同响应
            second = await client.post(
                "/api/v1/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "idem-api-1",
                },
                json={
                    "items": [
                        {"product_id": 101, "quantity": 1, "spec_option_ids": [101]},
                    ],
                    "order_type": "pickup",
                    "notes": "无糖",
                },
            )
            assert second.status_code == 200
            assert second.json()["order_id"] == order_id
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_create_order_api_requires_guest_session(db_session) -> None:
    await _seed_product(db_session)
    guest_session = IdempotencyKey(
        idempotency_key="gs-test",
        scope="guest_session",
    )
    db_session.add(guest_session)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            without_session = await client.post(
                "/api/v1/orders",
                headers={"Idempotency-Key": "idem-guest-1"},
                json={
                    "items": [{"product_id": 101, "quantity": 1, "spec_option_ids": []}],
                    "order_type": "pickup",
                },
            )
            assert without_session.status_code == 400

            with_session = await client.post(
                "/api/v1/orders",
                headers={"Idempotency-Key": "idem-guest-2"},
                json={
                    "items": [{"product_id": 101, "quantity": 1, "spec_option_ids": []}],
                    "order_type": "pickup",
                    "guest_session_id": "gs-test",
                },
            )
            assert with_session.status_code == 200
            data = with_session.json()
            assert data["items"][0]["product_id"] == 101
    finally:
        app.dependency_overrides.pop(get_async_session, None)
