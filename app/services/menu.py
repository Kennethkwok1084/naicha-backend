from __future__ import annotations

import copy
import time
from collections import defaultdict
from threading import Lock
from typing import Any

import redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from structlog import get_logger

from app.core.settings import Settings, get_settings
from app.metrics.menu import record_cache_hit, record_cache_miss
from app.models.catalog import (
    Category,
    Product,
    ProductSpecMapping,
    SpecGroup,
    SpecOption,
)

logger = get_logger(__name__)

_MENU_CACHE: dict[str, tuple[float, int | None, dict[str, Any]]] = {}

_MENU_VERSION_KEY = "menu:version"
_menu_version_lock = Lock()
_menu_version_client: redis.Redis | None = None
_menu_version_disabled = False


def _disable_menu_version_tracking() -> None:
    global _menu_version_disabled, _menu_version_client
    _menu_version_disabled = True
    _menu_version_client = None


def _get_version_client(settings: Settings) -> redis.Redis | None:
    global _menu_version_client
    if _menu_version_disabled:
        return None
    client = _menu_version_client
    if client is not None:
        return client
    with _menu_version_lock:
        client = _menu_version_client
        if client is not None:
            return client
        try:
            client = redis.Redis.from_url(settings.celery_broker_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - 初始化失败仅记录
            logger.warning("menu.cache.version_client_init_failed", error=str(exc))
            _disable_menu_version_tracking()
            return None
        _menu_version_client = client
        return client


def _read_remote_menu_version(settings: Settings) -> int | None:
    client = _get_version_client(settings)
    if client is None:
        return None
    try:
        value = client.get(_MENU_VERSION_KEY)
        if value is None:
            client.set(_MENU_VERSION_KEY, "0", nx=True)
            value = client.get(_MENU_VERSION_KEY)
        if value is None:
            return None
        return int(value)
    except (RedisError, ValueError) as exc:
        logger.warning("menu.cache.version_read_failed", error=str(exc))
        _disable_menu_version_tracking()
        return None


def _bump_remote_menu_version(settings: Settings) -> None:
    client = _get_version_client(settings)
    if client is None:
        return
    try:
        client.incr(_MENU_VERSION_KEY)
    except RedisError as exc:
        logger.warning("menu.cache.version_bump_failed", error=str(exc))
        _disable_menu_version_tracking()


def invalidate_menu_cache(settings: Settings | None = None) -> None:
    _MENU_CACHE.clear()
    active_settings = settings or get_settings()
    _bump_remote_menu_version(active_settings)


class MenuService:
    CACHE_KEY = "menu"

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._remote_version_snapshot: int | None = None

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
        expires_at, cached_version, payload = entry
        if expires_at < time.time():
            _MENU_CACHE.pop(self.CACHE_KEY, None)
            record_cache_miss()
            return None

        remote_version = self._fetch_remote_version()
        if remote_version is not None and cached_version != remote_version:
            _MENU_CACHE.pop(self.CACHE_KEY, None)
            record_cache_miss()
            return None

        record_cache_hit()
        return payload

    def _store_to_cache(self, payload: dict[str, Any]) -> None:
        ttl = max(self._settings.menu_cache_ttl_seconds, 0)
        expires_at = time.time() + ttl
        version = self._remote_version_snapshot
        if version is None:
            version = self._fetch_remote_version()
        _MENU_CACHE[self.CACHE_KEY] = (expires_at, version, payload)

    def _fetch_remote_version(self) -> int | None:
        version = _read_remote_menu_version(self._settings)
        self._remote_version_snapshot = version
        return version
