from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from app.core.settings import get_settings
from app.models.accounts import Coupon, User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.orders import IdempotencyKey, Order
from app.models.reservations import ReservationSlot
from app.models.shop import ShopProfile
from app.schemas import (
    OrderAddressSchema,
    OrderCalculateRequestSchema,
    OrderCreateRequestSchema,
    OrderItemCreateSchema,
    OrderPaymentJsapiRequestSchema,
    OrderPaymentNativeRequestSchema,
)
from app.services.orders import (
    OrderOwnershipError,
    OrderService,
    OrderValidationError,
)
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _seed_menu(db_session):
    category = Category(category_id=1, name="奶茶", sort_order=1)
    product = Product(
        product_id=1,
        category_id=category.category_id,
        name="招牌奶茶",
        description="热销",
        base_price=Decimal("12.00"),
        status="active",
        inventory_status="in_stock",
        stock_quantity=50,
    )
    group = SpecGroup(group_id=1, name="甜度", sort_order=1)
    option = SpecOption(
        option_id=1,
        group_id=group.group_id,
        name="半糖",
        price_modifier=Decimal("1.00"),
        inventory_status="in_stock",
        sort_order=1,
    )
    mapping = ProductSpecMapping(mapping_id=1, product_id=product.product_id, group_id=group.group_id)

    db_session.add_all([category, product, group, option, mapping])
    await db_session.flush()


@pytest.mark.asyncio
async def test_create_order_with_idempotency(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=1, open_id="openid-user")
    db_session.add(user)
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCreateRequestSchema(
        items=[
            OrderItemCreateSchema(product_id=1, quantity=2, spec_option_ids=[1]),
        ],
        order_type="pickup",
        notes="少冰",
    )

    first = await service.create_order(payload=payload, idempotency_key="idem-001", user=user)
    assert first["order_id"] > 0
    assert first["total_price"] == 26.0  # 12 + 1 = 13, quantity 2
    assert first["is_scheduled"] is False

    second = await service.create_order(payload=payload, idempotency_key="idem-001", user=user)
    assert second == first


@pytest.mark.asyncio
async def test_create_order_idempotency_race_condition(model_test_engine) -> None:
    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    if model_test_engine.dialect.name == "sqlite":
        pytest.skip("SQLite 无法可靠模拟幂等键并发锁场景。")

    async with session_factory() as setup_session:
        async with setup_session.begin():
            await _seed_menu(setup_session)
            user = User(user_id=101, open_id="race-user")
            setup_session.add(user)

    settings = get_settings()

    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[1])],
        order_type="pickup",
        notes="race",
    )

    async def create_once():
        async with session_factory() as session:
            user = await session.get(User, 101)
            assert user is not None
            service = OrderService(session, settings)
            return await service.create_order(
                payload=payload,
                idempotency_key="idem-race",
                user=user,
            )

    first, second = await asyncio.gather(create_once(), create_once())
    assert first == second

    async with session_factory() as verify_session:
        record = await verify_session.get(IdempotencyKey, "idem-race")
    assert record is not None
    assert record.response_snapshot is not None


@pytest.mark.asyncio
async def test_create_order_deducts_product_stock(db_session) -> None:
    await _seed_menu(db_session)
    product = await db_session.get(Product, 1)
    assert product is not None
    product.stock_quantity = 2
    db_session.add(product)
    await db_session.flush()

    user = User(user_id=5, open_id="stock-user")
    db_session.add(user)
    await db_session.flush()

    service = OrderService(db_session, get_settings())

    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[1])],
        order_type="pickup",
    )
    result = await service.create_order(payload=payload, idempotency_key="stock-1", user=user)
    assert result["order_id"] > 0

    await db_session.refresh(product)
    assert product.stock_quantity == 1
    assert product.inventory_status == "in_stock"

    payload_second = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[1])],
        order_type="pickup",
    )
    await service.create_order(payload=payload_second, idempotency_key="stock-2", user=user)
    await db_session.refresh(product)
    assert product.stock_quantity == 0
    assert product.inventory_status == "sold_out"

    payload_third = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[1])],
        order_type="pickup",
    )
    with pytest.raises(OrderValidationError):
        await service.create_order(payload=payload_third, idempotency_key="stock-3", user=user)


@pytest.mark.asyncio
async def test_create_order_requires_guest_session(db_session) -> None:
    await _seed_menu(db_session)
    service = OrderService(db_session, get_settings())

    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
        order_type="pickup",
    )

    with pytest.raises(OrderValidationError):
        await service.create_order(payload=payload, idempotency_key="idem-guest", user=None)


@pytest.mark.asyncio
async def test_initiate_payment_requires_owner(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=1, open_id="owner-openid")
    other = User(user_id=2, open_id="other-openid")
    db_session.add_all([user, other])
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
        order_type="pickup",
    )

    order = await service.create_order(payload=payload, idempotency_key="idem-pay", user=user)

    jsapi_response = await service.initiate_wechat_jsapi_payment(
        order_id=order["order_id"],
        actor=user,
        request=OrderPaymentJsapiRequestSchema(payer_open_id="wx-openid"),
    )
    assert jsapi_response["channel"] == "wechat_jsapi"

    native_response = await service.initiate_wechat_native_payment(
        order_id=order["order_id"],
        actor=user,
        request=OrderPaymentNativeRequestSchema(),
    )
    assert native_response["channel"] == "wechat_native"

    with pytest.raises(OrderOwnershipError):
        await service.initiate_wechat_jsapi_payment(
            order_id=order["order_id"],
            actor=other,
            request=OrderPaymentJsapiRequestSchema(payer_open_id="wx2"),
        )


def test_generate_order_number_uniqueness() -> None:
    pattern = re.compile(r"^\d{17}-NA[A-F0-9]{6}$")
    numbers = {OrderService._generate_order_number() for _ in range(2000)}
    assert len(numbers) == 2000
    for order_number in numbers:
        assert pattern.match(order_number), f"unexpected format: {order_number}"


@pytest.mark.asyncio
async def test_create_reservation_requires_flag(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=2, open_id="reservation-user")
    db_session.add(user)
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
        order_type="pickup",
        scheduled_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )

    with pytest.raises(OrderValidationError):
        await service.create_order(payload=payload, idempotency_key="idem-resv", user=user)


@pytest.mark.asyncio
async def test_create_reservation_order_success(db_session) -> None:
    await _seed_menu(db_session)

    profile = ShopProfile(
        id=1,
        timezone="Asia/Shanghai",
        open_hours_json=[{"weekday": datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoweekday(), "ranges": [["08:00", "22:00"]]}],
    )
    db_session.add(profile)
    await db_session.flush()

    user = User(user_id=42, open_id="user-reservation")
    db_session.add(user)
    await db_session.flush()

    settings = get_settings()
    original_flag = settings.reservation_enabled
    try:
        settings.reservation_enabled = True
        service = OrderService(db_session, settings)
        scheduled_local = datetime.now(tz=ZoneInfo("Asia/Shanghai")) + timedelta(hours=2)
        payload = OrderCreateRequestSchema(
            items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
            order_type="pickup",
            scheduled_at=scheduled_local,
        )

        result = await service.create_order(
            payload=payload,
            idempotency_key="idem-reservation-ok",
            user=user,
        )
    finally:
        settings.reservation_enabled = original_flag

    assert result["is_scheduled"] is True
    assert result["scheduled_at"] is not None
    scheduled_utc = datetime.fromisoformat(result["scheduled_at"])
    assert scheduled_utc.tzinfo is not None
    assert scheduled_utc > datetime.now(tz=UTC)
    order = await db_session.get(Order, result["order_id"])
    assert order is not None
    assert order.reservation_slot_id is not None
    slot = await db_session.get(ReservationSlot, order.reservation_slot_id)
    assert slot is not None
    assert slot.reserved_count == 1


@pytest.mark.asyncio
async def test_reservation_slot_capacity_enforced(db_session) -> None:
    await _seed_menu(db_session)
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
    db_session.add(profile)
    user = User(user_id=77, open_id="reservation-cap")
    db_session.add(user)
    await db_session.flush()

    settings = get_settings()
    original_flag = settings.reservation_enabled
    original_capacity = settings.reservation_slot_capacity
    try:
        settings.reservation_enabled = True
        settings.reservation_slot_capacity = 1
        service = OrderService(db_session, settings)
        scheduled_local = datetime.now(tz=ZoneInfo("Asia/Shanghai")) + timedelta(hours=3)
        payload = OrderCreateRequestSchema(
            items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
            order_type="pickup",
            scheduled_at=scheduled_local,
        )

        await service.create_order(
            payload=payload,
            idempotency_key="idem-slot-1",
            user=user,
        )

        with pytest.raises(OrderValidationError):
            await service.create_order(
                payload=payload,
                idempotency_key="idem-slot-2",
                user=user,
            )
    finally:
        settings.reservation_enabled = original_flag
        settings.reservation_slot_capacity = original_capacity


@pytest.mark.asyncio
async def test_cancel_reservation_releases_slot(db_session) -> None:
    await _seed_menu(db_session)
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
    db_session.add(profile)
    user = User(user_id=88, open_id="reservation-cancel")
    db_session.add(user)
    await db_session.flush()

    settings = get_settings()
    original_flag = settings.reservation_enabled
    original_capacity = settings.reservation_slot_capacity
    try:
        settings.reservation_enabled = True
        settings.reservation_slot_capacity = 1
        service = OrderService(db_session, settings)
        scheduled_local = datetime.now(tz=ZoneInfo("Asia/Shanghai")) + timedelta(hours=4)
        payload = OrderCreateRequestSchema(
            items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
            order_type="pickup",
            scheduled_at=scheduled_local,
        )

        created = await service.create_order(
            payload=payload,
            idempotency_key="idem-slot-cancel",
            user=user,
        )
        order_row = await db_session.get(Order, created["order_id"])
        assert order_row is not None and order_row.reservation_slot_id is not None
        slot_id = order_row.reservation_slot_id

        cancelled = await service.cancel_pending_order(order_row.order_id, reason="test.manual")
        assert cancelled is True
        await db_session.refresh(order_row)
        assert order_row.status == "cancelled"
        assert order_row.reservation_slot_id is None

        slot = await db_session.get(ReservationSlot, slot_id)
        assert slot is not None
        assert slot.reserved_count == 0

        second = await service.create_order(
            payload=payload,
            idempotency_key="idem-slot-cancel-2",
            user=user,
        )
        assert second["order_id"] != created["order_id"]
    finally:
        settings.reservation_enabled = original_flag
        settings.reservation_slot_capacity = original_capacity


@pytest.mark.asyncio
async def test_create_order_holds_inventory_lock_until_commit(db_session) -> None:
    if db_session.bind.dialect.name == "sqlite":
        pytest.skip("SQLite 不支持行级锁,跳过该验证。")

    await _seed_menu(db_session)

    user = User(user_id=99, open_id="lock-user")
    db_session.add(user)
    await db_session.flush()

    settings = get_settings()
    service = OrderService(db_session, settings)

    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
        order_type="pickup",
    )

    ready_event = asyncio.Event()
    release_event = asyncio.Event()

    async def post_create(order, items):
        ready_event.set()
        await release_event.wait()

    order_task = asyncio.create_task(
        service.create_order(
            payload=payload,
            idempotency_key="idem-lock",
            user=user,
            post_create=post_create,
        )
    )

    await asyncio.wait_for(ready_event.wait(), timeout=1.0)

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def update_inventory():
        async with session_factory() as other_session:
            async with other_session.begin():
                product = await other_session.get(Product, 1)
                product.inventory_status = "sold_out"
                await other_session.flush()

    update_task = asyncio.create_task(update_inventory())

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(update_task), timeout=0.1)

    release_event.set()

    order_result = await asyncio.wait_for(order_task, timeout=1.0)
    assert order_result["order_id"] > 0

    await asyncio.wait_for(update_task, timeout=1.0)


@pytest.mark.asyncio
async def test_cancel_pending_order_restores_inventory(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=301, open_id="cancel-user")
    db_session.add(user)
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=2, spec_option_ids=[])],
        order_type="pickup",
    )

    created = await service.create_order(payload=payload, idempotency_key="idem-cancel", user=user)
    product = await db_session.get(Product, 1)
    assert product is not None
    assert product.stock_quantity == 48

    cancelled = await service.cancel_pending_order(created["order_id"], reason="test.manual")
    assert cancelled is True

    await db_session.refresh(product)
    assert product.stock_quantity == 50

    order_entity = await db_session.get(Order, created["order_id"])
    assert order_entity is not None
    assert order_entity.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_stale_pending_orders_respects_cutoff(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=302, open_id="stale-user")
    db_session.add(user)
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCreateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[])],
        order_type="pickup",
    )
    created = await service.create_order(payload=payload, idempotency_key="idem-stale", user=user)

    order_entity = await db_session.get(Order, created["order_id"])
    assert order_entity is not None
    order_entity.created_at = datetime.now(tz=UTC) - timedelta(hours=2)
    await db_session.flush()

    cutoff = datetime.now(tz=UTC) - timedelta(minutes=30)
    cancelled_ids = await service.cancel_stale_pending_orders(cutoff, limit=10)
    assert created["order_id"] in cancelled_ids

    product = await db_session.get(Product, 1)
    assert product is not None
    assert product.stock_quantity == 50


@pytest.mark.asyncio
async def test_calculate_price_basic_breakdown(db_session) -> None:
    await _seed_menu(db_session)
    service = OrderService(db_session, get_settings())
    payload = OrderCalculateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=2, spec_option_ids=[1])],
        order_type="pickup",
    )

    result = await service.calculate_price_only(payload=payload, user=None)

    assert result["subtotal"] == 26.0
    assert result["final_amount"] == 26.0
    assert len(result["breakdown"]) == 1
    assert result["breakdown"][0]["unit_price"] == 13.0


@pytest.mark.asyncio
async def test_calculate_price_applies_coupon_discount(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=401, open_id="coupon-user")
    coupon = Coupon(user_id=user.user_id, type="free_any_drink", status="active")
    db_session.add_all([user, coupon])
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCalculateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=2, spec_option_ids=[1])],
        order_type="pickup",
        coupon_id=coupon.coupon_id,
    )

    result = await service.calculate_price_only(payload=payload, user=user)

    assert result["coupon_discount"] == 13.0
    assert result["final_amount"] == 13.0
    assert result["coupon_info"] is not None
    assert result["coupon_info"]["is_applicable"] is True


@pytest.mark.asyncio
async def test_calculate_price_applies_points_cap(db_session) -> None:
    await _seed_menu(db_session)
    user = User(user_id=402, open_id="points-user", loyalty_points=800)
    db_session.add(user)
    await db_session.flush()

    service = OrderService(db_session, get_settings())
    payload = OrderCalculateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=2, spec_option_ids=[1])],
        order_type="pickup",
        points_use=600,
    )

    result = await service.calculate_price_only(payload=payload, user=user)

    assert result["points_discount"] == 6.0
    assert result["final_amount"] == 20.0
    assert result["points_info"] is not None
    assert result["points_info"]["used"] == 600


@pytest.mark.asyncio
async def test_calculate_price_delivery_fee(db_session) -> None:
    await _seed_menu(db_session)
    service = OrderService(db_session, get_settings())
    payload = OrderCalculateRequestSchema(
        items=[OrderItemCreateSchema(product_id=1, quantity=1, spec_option_ids=[1])],
        order_type="delivery",
        address=OrderAddressSchema(
            province="广东省",
            city="深圳市",
            district="南山区",
            detail="科技园",
        ),
    )

    result = await service.calculate_price_only(payload=payload, user=None)

    assert result["delivery_fee"] == 6.0
    assert result["final_amount"] == pytest.approx(19.0)
