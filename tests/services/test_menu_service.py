from __future__ import annotations

import time
from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.models import catalog as catalog_module
from app.models.catalog import (
    Category,
    Product,
    ProductCategory,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)
from app.services import menu as menu_module
from app.services.menu import _MENU_CACHE, MenuService, invalidate_menu_cache


async def _seed_basic_menu(db_session) -> None:
    category = Category(category_id=10, name="茶饮", sort_order=1)
    product = Product(
        product_id=10,
        category_id=10,
        name="黑糖珍珠鲜奶",
        description="热销",
        base_price=Decimal("18.50"),
        status="active",
        inventory_status="in_stock",
    )
    product_inactive = Product(
        product_id=99,
        name="下架饮品",
        base_price=Decimal("10"),
        status="inactive",
        inventory_status="in_stock",
    )
    spec_group = SpecGroup(group_id=10, name="甜度", sort_order=1)
    spec_option = SpecOption(
        option_id=10,
        group_id=spec_group.group_id,
        name="半糖",
        price_modifier=Decimal("0"),
        inventory_status="in_stock",
        sort_order=1,
    )
    mapping = ProductSpecMapping(mapping_id=10, product_id=product.product_id, group_id=spec_group.group_id)
    product_category = ProductCategory(product_id=product.product_id, category_id=category.category_id)

    uncategorized = Product(
        product_id=11,
        name="单点小料",
        base_price=Decimal("3.00"),
        status="active",
        inventory_status="in_stock",
    )

    db_session.add_all(
        [
            category,
            product,
            product_inactive,
            spec_group,
            spec_option,
            mapping,
            product_category,
            uncategorized,
        ]
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_menu_service_builds_payload_with_multi_category(db_session) -> None:
    invalidate_menu_cache()
    await _seed_basic_menu(db_session)

    settings = get_settings().model_copy()
    service = MenuService(db_session, settings)

    payload = await service.get_menu_payload()
    assert payload["multi_category_enabled"] is True
    assert payload["categories"][0]["products"][0]["name"] == "黑糖珍珠鲜奶"
    assert payload["categories"][0]["products"][0]["spec_groups"][0]["options"][0]["name"] == "半糖"
    assert any(product["name"] == "单点小料" for product in payload["uncategorized_products"])

    cached = await service.get_menu_payload()
    assert cached is payload  # 命中缓存直接返回同一对象


@pytest.mark.asyncio
async def test_menu_service_respects_single_category_mode(db_session) -> None:
    invalidate_menu_cache()
    await _seed_basic_menu(db_session)

    settings = get_settings().model_copy(update={"multi_category_enabled": False})
    service = MenuService(db_session, settings)

    payload = await service.get_menu_payload()
    # 单分类模式下依赖 product.category_id
    assert payload["categories"][0]["products"][0]["name"] == "黑糖珍珠鲜奶"
    assert payload["multi_category_enabled"] is False


@pytest.mark.asyncio
async def test_menu_service_cache_expires(db_session) -> None:
    invalidate_menu_cache()
    await _seed_basic_menu(db_session)

    settings = get_settings().model_copy()
    service = MenuService(db_session, settings)

    # 预先写入过期缓存,触发过期清理分支
    _MENU_CACHE[MenuService.CACHE_KEY] = (time.time() - 1, 0, {"stale": True})
    payload = await service.get_menu_payload()

    assert payload["categories"]
    assert MenuService.CACHE_KEY in _MENU_CACHE
    assert _MENU_CACHE[MenuService.CACHE_KEY][2] == payload


def test_catalog_events_trigger_cache_invalidation(monkeypatch) -> None:
    calls: list[str] = []

    def fake_invalidate() -> None:
        calls.append("invalidate")

    monkeypatch.setattr(catalog_module, "_invalidate_menu_cache", fake_invalidate)

    product = object()
    option = object()

    catalog_module._product_status_change(product, "inactive", "active", None)
    assert calls == ["invalidate"]

    calls.clear()
    catalog_module._spec_option_inventory_status_change(option, "sold_out", "in_stock", None)
    assert calls == ["invalidate"]


@pytest.mark.asyncio
async def test_menu_cache_invalidates_when_remote_version_changes(monkeypatch, db_session) -> None:
    menu_module._menu_version_disabled = False
    menu_module._menu_version_client = None
    menu_module._MENU_CACHE.clear()

    version_state = {"value": 0}

    def fake_read(settings):
        return version_state["value"]

    def fake_bump(settings):
        version_state["value"] += 1

    monkeypatch.setattr(menu_module, "_read_remote_menu_version", fake_read)
    monkeypatch.setattr(menu_module, "_bump_remote_menu_version", fake_bump)

    invalidate_menu_cache()
    await _seed_basic_menu(db_session)

    settings = get_settings().model_copy()
    service = MenuService(db_session, settings)

    first_payload = await service.get_menu_payload()
    assert first_payload["categories"]

    cached = await service.get_menu_payload()
    assert cached is first_payload

    version_state["value"] += 1

    refreshed = await service.get_menu_payload()
    assert refreshed is not first_payload
