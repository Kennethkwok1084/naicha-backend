from __future__ import annotations

from decimal import Decimal

import pytest
from app.db.session import get_async_session
from app.main import app
from app.models.catalog import (
    Category,
    Product,
    ProductCategory,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)
from app.services.menu import invalidate_menu_cache
from httpx import ASGITransport, AsyncClient


async def _prepare_basic_menu(db_session) -> Product:
    category = Category(category_id=1, name="热销", sort_order=1)
    product = Product(
        product_id=1,
        name="珍珠奶茶",
        base_price=Decimal("12.50"),
        description="经典款",
        status="active",
        inventory_status="in_stock",
        stock_quantity=80,
    )
    mapping = ProductCategory(product_id=1, category_id=1)

    spec_group = SpecGroup(group_id=1, name="糖度", sort_order=1)
    spec_option = SpecOption(
        option_id=1,
        group_id=1,
        name="正常糖",
        price_modifier=Decimal("0.00"),
        inventory_status="in_stock",
        sort_order=1,
    )
    product_spec = ProductSpecMapping(mapping_id=1, product_id=1, group_id=1)

    db_session.add_all(
        [category, product, mapping, spec_group, spec_option, product_spec]
    )
    await db_session.flush()
    return product


@pytest.mark.asyncio
async def test_menu_endpoint_returns_expected_payload(db_session) -> None:
    invalidate_menu_cache()
    await _prepare_basic_menu(db_session)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/menu")
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["multi_category_enabled"] is True
    assert len(payload["categories"]) == 1
    category = payload["categories"][0]
    assert category["category_id"] == 1
    assert category["products"][0]["name"] == "珍珠奶茶"
    assert category["products"][0]["spec_groups"][0]["options"][0]["name"] == "正常糖"
    assert payload["uncategorized_products"] == []


@pytest.mark.asyncio
async def test_menu_cache_prevents_immediate_changes(db_session) -> None:
    invalidate_menu_cache()
    product = await _prepare_basic_menu(db_session)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get("/api/v1/menu")
            assert first.status_code == 200
            assert first.json()["categories"][0]["products"][0]["name"] == "珍珠奶茶"

            product.name = "焙香乌龙奶茶"
            await db_session.flush()

            second = await client.get("/api/v1/menu")
            assert second.json()["categories"][0]["products"][0]["name"] == "珍珠奶茶"

            invalidate_menu_cache()

            third = await client.get("/api/v1/menu")
            assert third.json()["categories"][0]["products"][0]["name"] == "焙香乌龙奶茶"
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_menu_cache_invalidate_on_inventory_change(db_session) -> None:
    invalidate_menu_cache()
    product = await _prepare_basic_menu(db_session)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get("/api/v1/menu")
            assert first.status_code == 200
            assert first.json()["categories"][0]["products"][0]["inventory_status"] == "in_stock"

            product.inventory_status = "sold_out"
            await db_session.flush()

            second = await client.get("/api/v1/menu")
            assert second.json()["categories"][0]["products"][0]["inventory_status"] == "sold_out"
    finally:
        app.dependency_overrides.pop(get_async_session, None)
