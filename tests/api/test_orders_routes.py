from __future__ import annotations

import asyncio
import hmac
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import TokenScope, create_access_token
from app.core.settings import get_settings
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import User
from app.models.catalog import (
    Category,
    Product,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)
from app.models.orders import IdempotencyKey, Order, OrderItem
from app.models.shop import ShopProfile
from app.schemas import WechatPaymentNotifySchema
from app.services.payments import PaymentService


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
        stock_quantity=100,
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
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [
                        {
                            "product_id": 101,
                            "quantity": 1,
                            "selected_specs": [
                                {"spec_id": 101, "option_id": 101, "option_name": "珍珠"}
                            ],
                        },
                    ],
                    "notes": "无糖",
                },
            )

            assert response.status_code == 201
            payload = response.json()
            assert payload["order_type"] == "pickup"
            assert payload["total_price"] == 17.0
            assert payload["items"][0]["product_id"] == 101
            assert payload["pickup_code"] is None
            assert payload["eta_minutes"] >= 1
            assert payload["eta_text"]

            order_id = payload["order_id"]
            order_number = payload["order_number"]

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
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [
                        {
                            "product_id": 101,
                            "quantity": 1,
                            "selected_specs": [{"spec_id": 101, "option_id": 101}],
                        },
                    ],
                    "notes": "无糖",
                },
            )
            assert second.status_code == 201
            assert second.json()["order_id"] == order_id

            detail_before = await client.get(
                f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert detail_before.status_code == 200
            assert detail_before.json()["pickup_code"] is None

            settings = get_settings()
            payment_service = PaymentService(db_session, settings)
            payment_payload = WechatPaymentNotifySchema(
                event_id="evt_api_paid",
                order_number=order_number,
                transaction_id="txn_api_1",
                amount=17.0,
                currency="CNY",
                channel="wechat_jsapi",
                status="SUCCESS",
                paid_at=datetime.now(tz=UTC),
            )
            raw_body = payment_payload.model_dump_json().encode("utf-8")
            signature = hmac.new(
                settings.secret_key.encode("utf-8"), raw_body, "sha256"
            ).hexdigest()
            payment_result = await payment_service.handle_wechat_notification(
                payment_payload, raw_body=raw_body, signature=signature
            )
            assert payment_result["status"] == "SUCCESS"

            detail_after = await client.get(
                f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert detail_after.status_code == 200
            assert detail_after.json()["pickup_code"]

            preview_resp = await client.post(
                "/api/v1/orders/preview",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [
                        {
                            "product_id": 101,
                            "quantity": 1,
                            "selected_specs": [{"spec_id": 101, "option_id": 101}],
                        },
                    ],
                    "notes": "无糖",
                },
            )
            assert preview_resp.status_code == 200
            assert preview_resp.json()["eta_minutes"] >= 1
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_create_order_api_idempotency_under_concurrency(model_test_engine) -> None:
    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    PRODUCT_ID = 502
    SPEC_OPTION_ID = 504

    async def _seed_concurrency_menu(session):
        category = Category(category_id=501, name="并发特调", sort_order=1)
        product = Product(
            product_id=PRODUCT_ID,
            category_id=category.category_id,
            name="并发奶茶",
            description="压力测试专用",
            base_price=Decimal("15.00"),
            status="active",
            inventory_status="in_stock",
            stock_quantity=200,
        )
        group = SpecGroup(group_id=503, name="加料-并发", sort_order=1)
        option = SpecOption(
            option_id=SPEC_OPTION_ID,
            group_id=group.group_id,
            name="燕麦",
            price_modifier=Decimal("1.00"),
            inventory_status="in_stock",
            sort_order=1,
        )
        mapping = ProductSpecMapping(
            mapping_id=504,
            product_id=product.product_id,
            group_id=group.group_id,
        )
        user = User(user_id=500, open_id="user-concurrent")
        session.add_all([category, product, group, option, mapping, user])
        await session.flush()
        await session.commit()

    token = create_access_token(subject="500", scope=TokenScope.USER)

    async def override_session():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_async_session] = override_session

    transport = ASGITransport(app=app)

    async with session_factory() as session:
        await _seed_concurrency_menu(session)

    async def _invoke(idx: int):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/v1/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": f"idem-concurrent-{idx}",
                },
                json={
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [
                        {
                            "product_id": PRODUCT_ID,
                            "quantity": 1,
                            "selected_specs": [{"spec_id": 503, "option_id": SPEC_OPTION_ID}],
                        },
                    ],
                    "notes": "并发下单",
                },
            )

    try:
        responses = await asyncio.gather(*[_invoke(i) for i in range(10)])
    finally:
        app.dependency_overrides.pop(get_async_session, None)
        if hasattr(transport, "close"):
            transport.close()

    assert all(response.status_code == 201 for response in responses)
    payloads = [resp.json() for resp in responses]
    order_ids = {payload["order_id"] for payload in payloads}
    assert len(order_ids) == 10


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
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [{"product_id": 101, "quantity": 1, "selected_specs": []}],
                },
            )
            assert without_session.status_code == 400

            with_session = await client.post(
                "/api/v1/orders",
                headers={"Idempotency-Key": "idem-guest-2"},
                json={
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [{"product_id": 101, "quantity": 1, "selected_specs": []}],
                    "guest_session_id": "gs-test",
                },
            )
            assert with_session.status_code == 201
            data = with_session.json()
            assert data["items"][0]["product_id"] == 101
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_create_order_api_reservation_success(db_session) -> None:
    await _seed_product(db_session)
    user = User(user_id=5000, open_id="user-reservation-api")
    profile = ShopProfile(
        id=1,
        timezone="Asia/Shanghai",
        open_hours_json=[
            {
                "weekday": datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoweekday(),
                "ranges": [["08:00", "22:00"]],
            }
        ],
    )
    db_session.add_all([user, profile])
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)
    settings = get_settings()
    original_flag = settings.reservation_enabled

    scheduled_local = datetime.now(tz=ZoneInfo("Asia/Shanghai")) + timedelta(hours=2)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        settings.reservation_enabled = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "idem-reservation-api",
                },
                json={
                    "shop_id": 1,
                    "delivery_type": "pickup",
                    "user_phone": "13800000000",
                    "items": [{"product_id": 101, "quantity": 1, "selected_specs": []}],
                    "scheduled_at": scheduled_local.isoformat(),
                },
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["is_scheduled"] is True
        assert payload["scheduled_at"].endswith("Z") or payload["scheduled_at"].endswith("+00:00")
    finally:
        settings.reservation_enabled = original_flag
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_cancel_order_success(db_session) -> None:
    """测试用户成功取消待支付订单"""
    await _seed_product(db_session)
    user = User(user_id=800, open_id="user-cancel")
    db_session.add(user)
    await db_session.flush()

    # 创建待支付订单
    order = Order(
        order_id=9200,
        order_number="TEST-CANCEL-1",
        user_id=user.user_id,
        total_price=17,
        status="pending_payment",
        order_type="pickup",
        payment_status="pending",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(),
        pickup_code="999888",
    )
    item = OrderItem(
        item_id=9201,
        order_id=order.order_id,
        product_id=101,
        product_name="桂花乌龙",
        quantity=1,
        unit_price=17,
        selected_specs_json=[{"spec_id": 101, "option_id": 101, "option_name": "珍珠"}],
    )
    db_session.add_all([order, item])
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/orders/{order.order_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cancelled"
        assert payload["order_id"] == order.order_id

    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_cancel_order_not_found(db_session) -> None:
    """测试取消不存在的订单"""
    user = User(user_id=801, open_id="user-cancel-404")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/orders/99999/cancel",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 404

    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_cancel_order_not_owner(db_session) -> None:
    """测试取消不属于自己的订单"""
    user1 = User(user_id=802, open_id="user-owner-1")
    user2 = User(user_id=803, open_id="user-owner-2")
    db_session.add_all([user1, user2])
    await db_session.flush()

    order = Order(
        order_id=9210,
        order_number="TEST-CANCEL-OWNER",
        user_id=user1.user_id,
        total_price=10,
        status="pending_payment",
        order_type="pickup",
        payment_status="pending",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(),
        pickup_code="888777",
    )
    item = OrderItem(
        item_id=9211,
        order_id=order.order_id,
        product_id=1,
        product_name="测试",
        quantity=1,
        unit_price=10,
        selected_specs_json=[],
    )
    db_session.add_all([order, item])
    await db_session.flush()

    token = create_access_token(subject=str(user2.user_id), scope=TokenScope.USER)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/orders/{order.order_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 403

    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_cancel_order_already_paid(db_session) -> None:
    """测试取消已支付订单(应失败)"""
    user = User(user_id=804, open_id="user-cancel-paid")
    db_session.add(user)
    await db_session.flush()

    order = Order(
        order_id=9220,
        order_number="TEST-CANCEL-PAID",
        user_id=user.user_id,
        total_price=10,
        status="paid",
        order_type="pickup",
        payment_status="paid",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(),
        pickup_code="777666",
    )
    item = OrderItem(
        item_id=9221,
        order_id=order.order_id,
        product_id=1,
        product_name="测试",
        quantity=1,
        unit_price=10,
        selected_specs_json=[],
    )
    db_session.add_all([order, item])
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/orders/{order.order_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 409

    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_cancel_order_as_guest(db_session) -> None:
    """测试游客取消订单"""
    order = Order(
        order_id=9230,
        order_number="TEST-CANCEL-GUEST",
        user_id=None,
        guest_session_id="guest_session_abc",
        total_price=10,
        status="pending_payment",
        order_type="pickup",
        payment_status="pending",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(),
        pickup_code="666555",
    )
    item = OrderItem(
        item_id=9231,
        order_id=order.order_id,
        product_id=1,
        product_name="测试",
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
            # 正确的 guest_session_id
            response = await client.post(
                f"/api/v1/orders/{order.order_id}/cancel?guest_session_id=guest_session_abc",
            )
            assert response.status_code == 200

    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_cancel_order_guest_session_mismatch(db_session) -> None:
    """测试游客会话不匹配"""
    order = Order(
        order_id=9240,
        order_number="TEST-CANCEL-GUEST-MISMATCH",
        user_id=None,
        guest_session_id="guest_session_xyz",
        total_price=10,
        status="pending_payment",
        order_type="pickup",
        payment_status="pending",
        source="user",
        is_scheduled=False,
        created_at=datetime.now(),
        pickup_code="555444",
    )
    item = OrderItem(
        item_id=9241,
        order_id=order.order_id,
        product_id=1,
        product_name="测试",
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
            # 错误的 guest_session_id
            response = await client.post(
                f"/api/v1/orders/{order.order_id}/cancel?guest_session_id=wrong_session",
            )
            assert response.status_code == 403

    finally:
        app.dependency_overrides.pop(get_async_session, None)
