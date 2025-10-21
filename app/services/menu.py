from __future__ import annotations

import copy
import time
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import Settings
from app.models.catalog import (
    Category,
    Product,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)
from app.metrics.menu import record_cache_hit, record_cache_miss

_MENU_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_menu_cache() -> None:
    _MENU_CACHE.clear()


class MenuService:
    CACHE_KEY = "menu"

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def get_menu_payload(self) -> dict[str, Any]:
        cached = self._load_from_cache()
        if cached is not None:
            return cached

        payload = await self._build_menu_payload()
        self._store_to_cache(payload)
        return payload

    async def _build_menu_payload(self) -> dict[str, Any]:
        categories = await self._session.execute(
            select(Category).order_by(Category.sort_order, Category.category_id)
        )
        categories_list = list(categories.scalars())

        product_stmt = (
            select(Product)
            .options(selectinload(Product.categories))
            .order_by(Product.product_id)
        )
        products_result = await self._session.execute(product_stmt)
        products = [product for product in products_result.scalars() if product.status == "active"]

        spec_groups_map = await self._load_spec_groups()
        product_spec_map = await self._load_product_spec_mappings()

        serialized_products: dict[int, dict[str, Any]] = {}
        uncategorized: list[dict[str, Any]] = []
        category_products: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)

        for product in products:
            spec_group_ids = product_spec_map.get(product.product_id, [])
            product_spec_groups = [
                self._clone_spec_group(spec_groups_map[group_id])
                for group_id in spec_group_ids
                if group_id in spec_groups_map
            ]

            product_payload = {
                "product_id": product.product_id,
                "name": product.name,
                "description": product.description,
                "image_url": product.image_url,
                "base_price": float(product.base_price),
                "status": product.status,
                "inventory_status": product.inventory_status,
                "spec_groups": product_spec_groups,
            }

            serialized_products[product.product_id] = product_payload

            category_ids: list[int] = []
            if self._settings.multi_category_enabled:
                category_ids = [category.category_id for category in product.categories]
            else:
                if product.category_id:
                    category_ids = [product.category_id]

            if not category_ids:
                uncategorized.append(product_payload)
                continue

            for category_id in category_ids:
                category_products[category_id].append(product_payload)

        categories_payload = []
        for category in categories_list:
            categories_payload.append(
                {
                    "category_id": category.category_id,
                    "name": category.name,
                    "sort_order": category.sort_order,
                    "products": category_products.get(category.category_id, []),
                }
            )

        return {
            "categories": categories_payload,
            "uncategorized_products": uncategorized,
            "multi_category_enabled": self._settings.multi_category_enabled,
        }

    async def _load_spec_groups(self) -> dict[int, dict[str, Any]]:
        result = await self._session.execute(
            select(SpecGroup).order_by(SpecGroup.sort_order, SpecGroup.group_id)
        )
        groups = result.scalars().all()

        options_result = await self._session.execute(
            select(SpecOption)
            .order_by(SpecOption.group_id, SpecOption.sort_order, SpecOption.option_id)
        )
        options = options_result.scalars().all()

        options_by_group: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
        for option in options:
            options_by_group[option.group_id].append(
                {
                    "option_id": option.option_id,
                    "name": option.name,
                    "price_modifier": float(option.price_modifier),
                    "inventory_status": option.inventory_status,
                    "sort_order": option.sort_order,
                }
            )

        spec_groups_map: dict[int, dict[str, Any]] = {}
        for group in groups:
            spec_groups_map[group.group_id] = {
                "group_id": group.group_id,
                "name": group.name,
                "sort_order": group.sort_order,
                "options": options_by_group.get(group.group_id, []),
            }
        return spec_groups_map

    async def _load_product_spec_mappings(self) -> dict[int, list[int]]:
        result = await self._session.execute(select(ProductSpecMapping))
        mappings = result.scalars().all()
        product_spec_map: defaultdict[int, list[int]] = defaultdict(list)
        for mapping in mappings:
            product_spec_map[mapping.product_id].append(mapping.group_id)
        return product_spec_map

    @staticmethod
    def _clone_spec_group(group: dict[str, Any]) -> dict[str, Any]:
        return {
            "group_id": group["group_id"],
            "name": group["name"],
            "sort_order": group["sort_order"],
            "options": [copy.deepcopy(option) for option in group["options"]],
        }

    def _load_from_cache(self) -> dict[str, Any] | None:
        entry = _MENU_CACHE.get(self.CACHE_KEY)
        if not entry:
            record_cache_miss()
            return None
        expires_at, payload = entry
        if expires_at < time.time():
            _MENU_CACHE.pop(self.CACHE_KEY, None)
            record_cache_miss()
            return None
        record_cache_hit()
        return payload

    def _store_to_cache(self, payload: dict[str, Any]) -> None:
        ttl = max(self._settings.menu_cache_ttl_seconds, 0)
        expires_at = time.time() + ttl
        _MENU_CACHE[self.CACHE_KEY] = (expires_at, payload)
