from __future__ import annotations

import re
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from app.core.settings import get_settings
from app.models.accounts import User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.shop import ShopProfile
from app.schemas import (
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
