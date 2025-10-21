from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin
from app.models.catalog import (
    Category,
    Product,
    ProductCategory,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)
from app.models.orders import AuditLog
from app.services.menu import invalidate_menu_cache
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


def _admin_token(admin_id: int) -> str:
    return create_access_token(subject=str(admin_id), scope=TokenScope.ADMIN)


async def _seed_menu(db_session) -> tuple[Product, SpecOption]:
    category = Category(category_id=3001, name="售罄测试", sort_order=1)
    product = Product(
        product_id=3001,
        name="阿萨姆奶茶",
        base_price=Decimal("16.50"),
        description="库存测试用",
        status="active",
        inventory_status="in_stock",
        category_id=category.category_id,
    )
    mapping = ProductCategory(product_id=product.product_id, category_id=category.category_id)

    spec_group = SpecGroup(group_id=3001, name="加料", sort_order=1)
    spec_option = SpecOption(
        option_id=3001,
        group_id=spec_group.group_id,
        name="燕麦",
        price_modifier=Decimal("1.50"),
        inventory_status="in_stock",
        sort_order=1,
    )
    product_spec = ProductSpecMapping(mapping_id=3001, product_id=product.product_id, group_id=spec_group.group_id)

    db_session.add_all([category, product, mapping, spec_group, spec_option, product_spec])
    await db_session.flush()
    return product, spec_option


@pytest.mark.asyncio
async def test_admin_updates_product_inventory_and_menu_reflects(db_session) -> None:
    invalidate_menu_cache()
    product, _ = await _seed_menu(db_session)
    admin = Admin(admin_id=801, username="inventory-admin", password_hash="x", role="admin")
    db_session.add(admin)
    await db_session.flush()

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            initial_menu = await client.get("/api/v1/menu")
            assert initial_menu.status_code == 200
            product_payload = _locate_product(initial_menu.json(), product.product_id)
            assert product_payload is not None
            assert product_payload["inventory_status"] == "in_stock"

            update = await client.put(
                f"/api/v1/admin/inventory/products/{product.product_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"inventory_status": "sold_out"},
            )
            assert update.status_code == 200, update.text
            payload = update.json()
            assert payload["inventory_status"] == "sold_out"
            assert payload["product_id"] == product.product_id
            assert payload["updated_at"]

            refreshed_menu = await client.get("/api/v1/menu")
            refreshed_payload = _locate_product(refreshed_menu.json(), product.product_id)
            assert refreshed_payload is not None
            assert refreshed_payload["inventory_status"] == "sold_out"

            revert = await client.put(
                f"/api/v1/admin/inventory/products/{product.product_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"inventory_status": "in_stock"},
            )
            assert revert.status_code == 200
            assert revert.json()["inventory_status"] == "in_stock"
            assert revert.json()["product_id"] == product.product_id

        audits = await db_session.execute(
            select(AuditLog).where(
                AuditLog.actor_admin_id == admin.admin_id,
                AuditLog.action == "admin.inventory.product.update",
            )
        )
        audit_records = list(audits.scalars())
        assert len(audit_records) >= 1
        assert audit_records[-1].after_json["inventory_status"] == "in_stock"
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_admin_updates_spec_option_inventory(db_session) -> None:
    invalidate_menu_cache()
    product, spec_option = await _seed_menu(db_session)
    admin = Admin(admin_id=802, username="inventory-spec", password_hash="x", role="manager")
    db_session.add(admin)
    await db_session.flush()

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            update = await client.put(
                f"/api/v1/admin/inventory/spec-options/{spec_option.option_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"inventory_status": "sold_out"},
            )
            assert update.status_code == 200
            body = update.json()
            assert body["spec_option_id"] == spec_option.option_id
            assert body["inventory_status"] == "sold_out"
            assert body["updated_at"]

            menu_resp = await client.get("/api/v1/menu")
            spec_product = _locate_product(menu_resp.json(), product.product_id)
            assert spec_product is not None
            spec_groups = spec_product["spec_groups"]
            assert spec_groups
            assert spec_groups[0]["options"][0]["inventory_status"] == "sold_out"
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_inventory_update_denied_for_clerk(db_session) -> None:
    invalidate_menu_cache()
    product, _ = await _seed_menu(db_session)
    clerk = Admin(admin_id=803, username="inventory-clerk", password_hash="x", role="clerk")
    db_session.add(clerk)
    await db_session.flush()

    token = _admin_token(clerk.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/admin/inventory/products/{product.product_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"inventory_status": "sold_out"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 403
    error = response.json()
    assert error["error"]["message"] == "Insufficient role for inventory updates."


def _locate_product(payload: dict, product_id: int) -> dict | None:
    for category in payload.get("categories", []):
        for item in category.get("products", []):
            if item.get("product_id") == product_id:
                return item
    for item in payload.get("uncategorized_products", []):
        if item.get("product_id") == product_id:
            return item
    return None
