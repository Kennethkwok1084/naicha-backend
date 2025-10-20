from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.models.accounts import User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
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
