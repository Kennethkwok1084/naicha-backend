from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_product_defaults_and_category_relationship(db_session) -> None:
    category = Category(category_id=1, name="热销", sort_order=1)
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    product = Product(
        product_id=1,
        name="珍珠奶茶",
        base_price=Decimal("12.00"),
        description="模型测试商品",
        category_id=category.category_id,
    )
    db_session.add(product)
    await db_session.flush()
    await db_session.refresh(product)

    assert product.status == "active"
    assert product.inventory_status == "in_stock"

    product.categories.append(category)
    await db_session.flush()

    await db_session.refresh(product)
    assert category in product.categories


@pytest.mark.asyncio
async def test_spec_option_constraints(db_session) -> None:
    group = SpecGroup(group_id=1, name="加料", sort_order=1)
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    option = SpecOption(
        option_id=1, group_id=group.group_id, name="波霸", price_modifier=Decimal("2.00")
    )
    db_session.add(option)
    await db_session.flush()
    await db_session.refresh(option)

    assert option.inventory_status == "in_stock"
    assert option.price_modifier == Decimal("2.00")

    duplicate_name = SpecOption(
        option_id=2, group_id=group.group_id, name="波霸", price_modifier=Decimal("1.00")
    )
    db_session.add(duplicate_name)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()

    other_group = SpecGroup(group_id=2, name="温度", sort_order=2)
    db_session.add(other_group)
    await db_session.flush()
    await db_session.refresh(other_group)

    invalid_inventory = SpecOption(
        option_id=3,
        group_id=other_group.group_id,
        name="温度非法",
        price_modifier=Decimal("0.00"),
        inventory_status="unknown",
    )
    db_session.add(invalid_inventory)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_product_spec_mapping_unique_constraint(db_session) -> None:
    product = Product(product_id=2, name="奶盖茶", base_price=Decimal("16.00"))
    group = SpecGroup(group_id=3, name="糖度", sort_order=1)
    db_session.add_all([product, group])
    await db_session.flush()
    await db_session.refresh(product)
    await db_session.refresh(group)

    mapping = ProductSpecMapping(
        mapping_id=1, product_id=product.product_id, group_id=group.group_id
    )
    db_session.add(mapping)
    await db_session.flush()

    duplicate_mapping = ProductSpecMapping(
        mapping_id=2, product_id=product.product_id, group_id=group.group_id
    )
    db_session.add(duplicate_mapping)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()
