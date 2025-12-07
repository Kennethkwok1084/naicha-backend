from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes.me import list_addresses
from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import User, UserAddress
from app.models.orders import Order, OrderItem
from app.services.user import UserService


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), scope=TokenScope.USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_profile_returns_user_info(db_session) -> None:
    user = User(user_id=101, open_id="openid-me-1", nickname="测试用户", loyalty_points=15)
    db_session.add(user)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/profile", headers=_auth_header(user.user_id))
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["loyalty_points"] == 15
    assert payload["user_id"] == user.user_id


@pytest.mark.asyncio
async def test_get_addresses_returns_list(db_session) -> None:
    user = User(user_id=201, open_id="openid-me-2")
    db_session.add(user)
    await db_session.flush()

    address = UserAddress(
        address_id=1,
        user_id=user.user_id,
        contact_name="张三",
        phone="13800000000",
        address_line="上海市徐汇区",
        is_default=True,
    )
    db_session.add(address)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/addresses", headers=_auth_header(user.user_id))
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["contact_name"] == "张三"


@pytest.mark.asyncio
async def test_me_endpoints_require_auth(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/profile")
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoints_reject_expired_token(db_session) -> None:
    user = User(user_id=301, open_id="openid-expired")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(
        subject=str(user.user_id),
        scope=TokenScope.USER,
        expires_delta=timedelta(seconds=-1),
    )

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/me/profile", headers={"Authorization": f"Bearer {token}"}
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Token expired"


@pytest.mark.asyncio
async def test_me_endpoints_reject_tampered_token(db_session) -> None:
    user = User(user_id=302, open_id="openid-tampered")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER) + "tamper"

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/me/addresses", headers={"Authorization": f"Bearer {token}"}
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Token invalid"


@pytest.mark.asyncio
async def test_list_addresses_handler_direct(db_session) -> None:
    user = User(user_id=401, open_id="openid-direct")
    db_session.add(user)
    await db_session.flush()

    addr1 = UserAddress(
        address_id=11,
        user_id=user.user_id,
        contact_name="李四",
        phone="13900000000",
        address_line="北京市",
        lat=39.9,
        lng=116.4,
        is_default=False,
    )
    db_session.add(addr1)
    await db_session.flush()

    service = UserService(db_session)
    result = await list_addresses(current_user=user, service=service)

    assert len(result) == 1
    assert result[0].contact_name == "李四"


@pytest.mark.asyncio
async def test_address_crud_endpoints(db_session) -> None:
    user = User(user_id=501, open_id="openid-addr")
    db_session.add(user)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/me/addresses",
                headers=_auth_header(user.user_id),
                json={
                    "contact_name": "王五",
                    "phone": "13700000000",
                    "address_line": "杭州市西湖区",
                    "is_default": True,
                },
            )
            assert create_resp.status_code == 201
            address_id = create_resp.json()["address_id"]

            update_resp = await client.put(
                f"/api/v1/me/addresses/{address_id}",
                headers=_auth_header(user.user_id),
                json={"phone": "13711112222"},
            )
            assert update_resp.status_code == 200
            assert update_resp.json()["phone"] == "13711112222"

            delete_resp = await client.delete(
                f"/api/v1/me/addresses/{address_id}",
                headers=_auth_header(user.user_id),
            )
            assert delete_resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_my_orders_and_stamps(db_session) -> None:
    user = User(user_id=601, open_id="openid-orders")
    db_session.add(user)
    await db_session.flush()

    order = Order(
        order_id=9001,
        order_number="TEST-ORDER-1",
        user_id=user.user_id,
        total_price=10,
        status="paid",
        order_type="pickup",
        payment_status="paid",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(UTC),
        pickup_code="123456",
    )
    item = OrderItem(
        item_id=1,
        order_id=order.order_id,
        product_id=1,
        product_name="测试饮品",
        quantity=1,
        unit_price=10,
        selected_specs_json=[],
    )
    db_session.add_all([order, item])
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            orders_resp = await client.get(
                "/api/v1/me/orders",
                headers=_auth_header(user.user_id),
            )
            assert orders_resp.status_code == 200
            assert len(orders_resp.json()) >= 1
            stamps_resp = await client.get("/api/v1/me/stamps", headers=_auth_header(user.user_id))
            assert stamps_resp.status_code == 200
            assert stamps_resp.json()["total_completed_orders"] >= 0
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_list_orders_with_status_filter(db_session) -> None:
    """测试订单状态筛选功能"""
    user = User(user_id=701, open_id="openid-status-filter")
    db_session.add(user)
    await db_session.flush()

    # 创建不同状态的订单
    order_pending = Order(
        order_id=9101,
        order_number="TEST-PENDING-1",
        user_id=user.user_id,
        total_price=10,
        status="pending_payment",
        order_type="pickup",
        payment_status="pending",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(UTC),
        pickup_code="123456",
    )
    order_paid = Order(
        order_id=9102,
        order_number="TEST-PAID-1",
        user_id=user.user_id,
        total_price=20,
        status="paid",
        order_type="pickup",
        payment_status="paid",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(UTC),
        pickup_code="123457",
    )
    order_cancelled = Order(
        order_id=9103,
        order_number="TEST-CANCELLED-1",
        user_id=user.user_id,
        total_price=30,
        status="cancelled",
        order_type="pickup",
        payment_status="pending",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(UTC),
        pickup_code="123458",
    )

    item1 = OrderItem(
        item_id=101,
        order_id=order_pending.order_id,
        product_id=1,
        product_name="测试饮品1",
        quantity=1,
        unit_price=10,
        selected_specs_json=[],
    )
    item2 = OrderItem(
        item_id=102,
        order_id=order_paid.order_id,
        product_id=1,
        product_name="测试饮品2",
        quantity=1,
        unit_price=20,
        selected_specs_json=[],
    )
    item3 = OrderItem(
        item_id=103,
        order_id=order_cancelled.order_id,
        product_id=1,
        product_name="测试饮品3",
        quantity=1,
        unit_price=30,
        selected_specs_json=[],
    )

    db_session.add_all([order_pending, order_paid, order_cancelled, item1, item2, item3])
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 测试单个状态筛选
            response = await client.get(
                "/api/v1/me/orders?status=pending_payment",
                headers=_auth_header(user.user_id),
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["status"] == "pending_payment"

            # 测试多个状态筛选
            response = await client.get(
                "/api/v1/me/orders?status=paid,cancelled",
                headers=_auth_header(user.user_id),
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            statuses = {order["status"] for order in data}
            assert statuses == {"paid", "cancelled"}

            # 测试无效状态
            response = await client.get(
                "/api/v1/me/orders?status=invalid_status",
                headers=_auth_header(user.user_id),
            )
            assert response.status_code == 400
            assert "Invalid status values" in response.json()["detail"]

            # 测试空状态列表(应返回所有订单，相当于不筛选)
            response = await client.get(
                "/api/v1/me/orders?status=",
                headers=_auth_header(user.user_id),
            )
            assert response.status_code == 200
            assert len(response.json()) == 3  # 所有订单

    finally:
        app.dependency_overrides.pop(get_async_session, None)
