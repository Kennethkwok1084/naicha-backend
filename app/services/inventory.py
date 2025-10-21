from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.accounts import Admin
from app.models.catalog import Product, SpecOption
from app.models.orders import AuditLog


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
