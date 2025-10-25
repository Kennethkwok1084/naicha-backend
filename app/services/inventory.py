from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.accounts import Admin
from app.models.catalog import Product, SpecOption
from app.models.orders import AuditLog, OrderItem


class InventoryError(Exception):
    """库存更新基础异常。"""


class InventoryNotFoundError(InventoryError):
    """目标不存在。"""


class InventoryService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def update_product_inventory(
        self,
        *,
        product_id: int,
        inventory_status: str,
        admin: Admin,
        ip: str | None,
        user_agent: str | None,
    ) -> Product:
        product = await self._session.get(Product, product_id)
        if product is None:
            raise InventoryNotFoundError("Product not found.")

        previous = product.inventory_status
        if previous == inventory_status:
            return product

        product.inventory_status = inventory_status
        product.updated_at = datetime.now(tz=UTC)

        audit = AuditLog(
            actor_type="admin",
            actor_admin_id=admin.admin_id,
            action="admin.inventory.product.update",
            target_table="products",
            target_id=str(product.product_id),
            before_json={"inventory_status": previous},
            after_json={"inventory_status": inventory_status},
            ip=ip,
            user_agent=user_agent,
        )
        self._session.add(audit)
        await self._session.flush()
        return product

    async def update_spec_option_inventory(
        self,
        *,
        option_id: int,
        inventory_status: str,
        admin: Admin,
        ip: str | None,
        user_agent: str | None,
    ) -> SpecOption:
        option = await self._session.get(SpecOption, option_id)
        if option is None:
            raise InventoryNotFoundError("Spec option not found.")

        previous = option.inventory_status
        if previous == inventory_status:
            return option

        option.inventory_status = inventory_status

        audit = AuditLog(
            actor_type="admin",
            actor_admin_id=admin.admin_id,
            action="admin.inventory.spec_option.update",
            target_table="spec_options",
            target_id=str(option.option_id),
            before_json={"inventory_status": previous},
            after_json={"inventory_status": inventory_status},
            ip=ip,
            user_agent=user_agent,
        )
        self._session.add(audit)
        await self._session.flush()
        return option

    async def restore_from_order_items(
        self,
        items: Sequence[OrderItem],
        *,
        dialect_name: str | None = None,
    ) -> list[dict[str, Any]]:
        product_deltas: dict[int, int] = {}
        for item in items:
            if item.product_id is None:
                continue
            product_deltas[item.product_id] = product_deltas.get(item.product_id, 0) + max(
                int(item.quantity or 0), 0
            )

        if not product_deltas:
            return []

        resolved_dialect = dialect_name
        if resolved_dialect is None:
            bind = self._session.get_bind()
            resolved_dialect = bind.dialect.name if bind is not None else ""

        stmt = select(Product).where(Product.product_id.in_(product_deltas))
        if resolved_dialect != "sqlite":
            stmt = stmt.with_for_update(of=Product)

        result = await self._session.execute(stmt)
        products = list(result.scalars().all())

        changes: list[dict[str, Any]] = []
        now = datetime.now(tz=UTC)

        for product in products:
            delta = product_deltas.get(product.product_id, 0)
            if delta <= 0:
                continue
            stock_before = getattr(product, "stock_quantity", None)
            if stock_before is None:
                continue
            product.stock_quantity = int(stock_before) + delta
            if product.stock_quantity > 0 and product.inventory_status == "sold_out":
                product.inventory_status = "in_stock"
            product.updated_at = now
            changes.append(
                {
                    "product_id": product.product_id,
                    "restored_quantity": delta,
                    "stock_before": int(stock_before),
                    "stock_after": int(product.stock_quantity),
                }
            )

        if changes:
            await self._session.flush()
        return changes
