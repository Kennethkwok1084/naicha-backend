from __future__ import annotations

import asyncio
import pytest
from app.core.settings import get_settings
from app.models.accounts import User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from app.schemas import OrderCreateRequestSchema, OrderItemCreateSchema
from app.services.orders import OrderService, OrderValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _seed_product(session, *, stock: int) -> None:
    category = Category(category_id=901, name="并发测试奶茶", sort_order=1)
    product = Product(
        product_id=901,
        category_id=category.category_id,
        name="并发测试产品",
        description="",
        base_price=10,
        status="active",
        inventory_status="in_stock",
        stock_quantity=stock,
    )
    group = SpecGroup(group_id=901, name="规格", sort_order=1)
    option = SpecOption(
        option_id=901,
        group_id=group.group_id,
        name="默认",
        price_modifier=0,
        inventory_status="in_stock",
        sort_order=1,
    )
    mapping = ProductSpecMapping(
        mapping_id=901,
        product_id=product.product_id,
        group_id=group.group_id,
    )
    session.add_all([category, product, group, option, mapping])


@pytest.mark.asyncio
async def test_concurrent_order_creation_respects_stock(model_test_engine) -> None:
    if model_test_engine.dialect.name == "sqlite":
        pytest.skip("SQLite 无法稳定复现行级锁,跳过并发库存测试。")

    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        async with setup_session.begin():
            await _seed_product(setup_session, stock=5)
            user = User(user_id=900, open_id="user-concurrency")
            setup_session.add(user)

    settings = get_settings()

    async def place_once(idx: int):
        async with session_factory() as session:
            user = await session.get(User, 900)
            assert user is not None
            service = OrderService(session, settings)
            payload = OrderCreateRequestSchema(
                items=[OrderItemCreateSchema(product_id=901, quantity=1, spec_option_ids=[901])],
                order_type="pickup",
            )
            try:
                return await service.create_order(
                    payload=payload,
                    idempotency_key=f"idem-concurrent-{idx}",
                    user=user,
                )
            except OrderValidationError as exc:
                return exc

    results = await asyncio.gather(*[place_once(i) for i in range(20)])
    successes = [r for r in results if not isinstance(r, OrderValidationError)]
    failures = [r for r in results if isinstance(r, OrderValidationError)]

    assert len(successes) == 5
    assert len(failures) == 15

    async with session_factory() as verify_session:
        product = await verify_session.get(Product, 901)
        assert product is not None
        assert product.stock_quantity == 0
        assert product.inventory_status == "sold_out"
