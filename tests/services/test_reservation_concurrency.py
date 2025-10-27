from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.core.settings import get_settings
from app.models.accounts import User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.shop import ShopProfile
from app.schemas import OrderCreateRequestSchema, OrderItemCreateSchema
from app.services.orders import OrderService, OrderValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _seed_menu(session, *, stock: int) -> None:
    category = Category(category_id=7101, name="预约并发", sort_order=1)
    product = Product(
        product_id=7101,
        category_id=category.category_id,
        name="预约并发测试",
        description="",
        base_price=12,
        status="active",
        inventory_status="in_stock",
        stock_quantity=stock,
    )
    group = SpecGroup(group_id=7101, name="规格", sort_order=1)
    option = SpecOption(
        option_id=7101,
        group_id=group.group_id,
        name="默认",
        price_modifier=0,
        inventory_status="in_stock",
        sort_order=1,
    )
    mapping = ProductSpecMapping(
        mapping_id=7101,
        product_id=product.product_id,
        group_id=group.group_id,
    )
    open_hours = [
        {
            "weekday": datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoweekday(),
            "ranges": [["08:00", "23:00"]],
        }
    ]
    profile = await session.get(ShopProfile, 1)
    if profile is None:
        profile = ShopProfile(id=1, timezone="Asia/Shanghai", open_hours_json=open_hours)
        session.add(profile)
    else:
        profile.timezone = "Asia/Shanghai"
        profile.open_hours_json = open_hours
    session.add_all([category, product, group, option, mapping])


@pytest.mark.asyncio
async def test_reservation_slot_concurrent_capacity(model_test_engine) -> None:
    if model_test_engine.dialect.name == "sqlite":
        pytest.skip("SQLite 无法覆盖行级锁场景")

    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        async with setup_session.begin():
            await _seed_menu(setup_session, stock=20)
            user = User(user_id=8800, open_id="user-reservation-concurrent")
            setup_session.add(user)

    settings = get_settings()
    original_flag = settings.reservation_enabled
    original_capacity = settings.reservation_slot_capacity
    try:
        settings.reservation_enabled = True
        settings.reservation_slot_capacity = 2

        async def place_once(idx: int):
            async with session_factory() as session:
                user = await session.get(User, 8800)
                assert user is not None
                service = OrderService(session, settings)
                scheduled_local = datetime.now(tz=ZoneInfo("Asia/Shanghai")) + timedelta(hours=1)
                payload = OrderCreateRequestSchema(
                    items=[
                        OrderItemCreateSchema(
                            product_id=7101,
                            quantity=1,
                            spec_option_ids=[7101],
                        )
                    ],
                    order_type="pickup",
                    scheduled_at=scheduled_local,
                )
                try:
                    return await service.create_order(
                        payload=payload,
                        idempotency_key=f"reserve-concurrent-{idx}",
                        user=user,
                    )
                except OrderValidationError as exc:
                    return exc

        results = await asyncio.gather(*[place_once(i) for i in range(6)])
        successes = [r for r in results if not isinstance(r, OrderValidationError)]
        failures = [r for r in results if isinstance(r, OrderValidationError)]

        assert len(successes) == settings.reservation_slot_capacity
        assert len(failures) == 6 - settings.reservation_slot_capacity
    finally:
        settings.reservation_enabled = original_flag
        settings.reservation_slot_capacity = original_capacity
