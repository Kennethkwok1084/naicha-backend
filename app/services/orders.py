from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.accounts import User
from app.models.catalog import Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.orders import IdempotencyKey, Order, OrderItem
from app.schemas.order import (
    OrderCreateRequestSchema,
    OrderPaymentJsapiRequestSchema,
    OrderPaymentNativeRequestSchema,
)


class OrderServiceError(Exception):
    """订单服务统一异常基类。"""


class OrderValidationError(OrderServiceError):
    """输入校验或状态校验失败。"""


class OrderConflictError(OrderServiceError):
    """存在幂等冲突或订单状态冲突。"""


class OrderNotFoundError(OrderServiceError):
    """订单不存在。"""


class OrderOwnershipError(OrderServiceError):
    """访问者无权操作该订单。"""


class OrderService:
    CREATE_SCOPE = "orders:create"
    GUEST_SCOPE = "guest_session"
    IDEMPOTENCY_TTL_HOURS = 24

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def create_order(
        self,
        *,
        payload: OrderCreateRequestSchema,
        idempotency_key: str,
        user: User | None,
    ) -> dict[str, Any]:
        if not idempotency_key.strip():
            raise OrderValidationError("Idempotency-Key header is required.")

        actor_guest_session = payload.guest_session_id
        if user is None and not actor_guest_session:
            raise OrderValidationError("guest_session_id is required for anonymous checkout.")
        if payload.order_type == "delivery" and payload.address is None:
            raise OrderValidationError("Delivery order requires address.")

        if actor_guest_session:
            await self._validate_guest_session(actor_guest_session)

        payload_dict = payload.model_dump()
        payload_hash = self._hash_payload(payload_dict)

        if self._session.in_transaction():
            return await self._create_order_internal(
                payload=payload,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                user=user,
                guest_session_id=actor_guest_session,
            )

        async with self._session.begin():
            return await self._create_order_internal(
                payload=payload,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                user=user,
                guest_session_id=actor_guest_session,
            )

    async def _create_order_internal(
        self,
        *,
        payload: OrderCreateRequestSchema,
        idempotency_key: str,
        payload_hash: str,
        user: User | None,
        guest_session_id: str | None,
    ) -> dict[str, Any]:
        
        idempotency_record, cached_response = await self._ensure_idempotency(
            idempotency_key, payload_hash
        )
        if cached_response is not None:
            return cached_response

        order = await self._build_order_entity(payload, user, guest_session_id)
        self._session.add(order)
        await self._session.flush()

        items_payload = payload.items
        specs_lookup = await self._load_spec_options(items_payload)
        product_groups = await self._load_product_groups(items_payload)
        products = await self._load_products_with_lock(items_payload)

        order_items = []
        total_price = Decimal("0.00")

        for item in items_payload:
            product = products.get(item.product_id)
            if product is None:
                raise OrderValidationError(f"Product {item.product_id} not found.")
            if product.status != "active":
                raise OrderValidationError(f"Product {item.product_id} is inactive.")
            if product.inventory_status != "in_stock":
                raise OrderValidationError(f"Product {item.product_id} is sold out.")

            allowed_groups = product_groups.get(item.product_id, set())
            selected_specs, modifiers_total = self._pick_spec_options(
                item.spec_option_ids,
                specs_lookup,
                allowed_groups,
                item.product_id,
            )

            unit_price = self._calculate_unit_price(product.base_price, modifiers_total)
            total_price += unit_price * item.quantity

            order_item = OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=unit_price,
                selected_specs_json=selected_specs,
            )
            order_items.append(order_item)
            self._session.add(order_item)

        order.total_price = total_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        await self._session.flush()
        await self._session.refresh(order)

        response_payload = self._build_order_response(order, order_items)
        idempotency_record.response_snapshot = response_payload

        return response_payload

    async def initiate_wechat_jsapi_payment(
        self,
        *,
        order_id: int,
        actor: User | None,
        request: OrderPaymentJsapiRequestSchema,
    ) -> dict[str, Any]:
        order = await self._session.get(Order, order_id)
        if order is None:
            raise OrderNotFoundError("Order not found.")

        self._ensure_order_access(order, actor, request.guest_session_id)
        self._ensure_order_pending(order)

        nonce = secrets.token_hex(8)
        timestamp = str(int(time.time()))
        raw = f"{order.order_number}:{request.payer_open_id}:{nonce}:{timestamp}"
        signature = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        return {
            "order_id": order.order_id,
            "channel": "wechat_jsapi",
            "payload": {
                "prepay_id": f"mock_prepay_{order.order_number}",
                "nonce_str": nonce,
                "timestamp": timestamp,
                "sign": signature,
                "payer_open_id": request.payer_open_id,
            },
        }

    async def initiate_wechat_native_payment(
        self,
        *,
        order_id: int,
        actor: User | None,
        request: OrderPaymentNativeRequestSchema,
    ) -> dict[str, Any]:
        order = await self._session.get(Order, order_id)
        if order is None:
            raise OrderNotFoundError("Order not found.")

        self._ensure_order_access(order, actor, request.guest_session_id)
        self._ensure_order_pending(order)

        return {
            "order_id": order.order_id,
            "channel": "wechat_native",
            "payload": {
                "code_url": f"https://pay.mock/wechat/native/{order.order_number}",
            },
        }

    async def _ensure_idempotency(
        self, key: str, payload_hash: str
    ) -> tuple[IdempotencyKey, dict[str, Any] | None]:
        record = await self._session.get(IdempotencyKey, key)
        expires_at = datetime.now(tz=UTC) + timedelta(hours=self.IDEMPOTENCY_TTL_HOURS)

        if record:
            if record.scope != self.CREATE_SCOPE:
                raise OrderConflictError("Idempotency key scope mismatch.")
            if record.request_hash and record.request_hash != payload_hash:
                raise OrderConflictError("Idempotency key reused with different payload.")

            record.request_hash = record.request_hash or payload_hash
            record.expire_at = expires_at
            if record.response_snapshot is not None:
                return record, record.response_snapshot
            return record, None

        record = IdempotencyKey(
            idempotency_key=key,
            scope=self.CREATE_SCOPE,
            request_hash=payload_hash,
            expire_at=expires_at,
        )
        self._session.add(record)
        return record, None

    async def _validate_guest_session(self, guest_session_id: str) -> None:
        record = await self._session.get(IdempotencyKey, guest_session_id)
        if not record or record.scope != self.GUEST_SCOPE:
            raise OrderValidationError("Guest session is invalid.")
        if record.expire_at and record.expire_at < datetime.now(tz=UTC):
            raise OrderValidationError("Guest session has expired.")

    async def _load_products_with_lock(self, items) -> dict[int, Product]:
        product_ids = {item.product_id for item in items}
        if not product_ids:
            return {}

        stmt = select(Product).where(Product.product_id.in_(product_ids))
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        products = {product.product_id: product for product in result.scalars().all()}
        return products

    async def _load_product_groups(self, items) -> dict[int, set[int]]:
        product_ids = {item.product_id for item in items}
        if not product_ids:
            return {}

        stmt = select(ProductSpecMapping).where(
            ProductSpecMapping.product_id.in_(product_ids)
        )
        result = await self._session.execute(stmt)
        product_groups: dict[int, set[int]] = {}
        for mapping in result.scalars():
            product_groups.setdefault(mapping.product_id, set()).add(mapping.group_id)
        return product_groups

    async def _load_spec_options(self, items) -> dict[int, tuple[SpecOption, SpecGroup | None]]:
        option_ids = {option_id for item in items for option_id in item.spec_option_ids}
        if not option_ids:
            return {}

        options_stmt = select(SpecOption).where(SpecOption.option_id.in_(option_ids))
        options_result = await self._session.execute(options_stmt)
        options = {option.option_id: option for option in options_result.scalars().all()}

        group_ids = {option.group_id for option in options.values()}
        groups: dict[int, SpecGroup] = {}
        if group_ids:
            group_stmt = select(SpecGroup).where(SpecGroup.group_id.in_(group_ids))
            group_result = await self._session.execute(group_stmt)
            groups = {group.group_id: group for group in group_result.scalars().all()}

        return {option_id: (option, groups.get(option.group_id)) for option_id, option in options.items()}

    async def _build_order_entity(
        self,
        payload: OrderCreateRequestSchema,
        user: User | None,
        guest_session_id: str | None,
    ) -> Order:
        order_number = self._generate_order_number()
        address_json = payload.address.model_dump() if payload.address else None

        order = Order(
            order_number=order_number,
            user_id=user.user_id if user else None,
            guest_session_id=None if user else guest_session_id,
            total_price=Decimal("0.00"),
            notes=payload.notes,
            status="pending_payment",
            order_type=payload.order_type,
            address_json=address_json,
        )
        return order

    def _pick_spec_options(
        self,
        option_ids: list[int],
        options_lookup: dict[int, tuple[SpecOption, SpecGroup | None]],
        allowed_groups: set[int],
        product_id: int,
    ) -> tuple[list[dict[str, Any]], Decimal]:
        selected_specs: list[dict[str, Any]] = []
        total_modifier = Decimal("0.00")

        for option_id in option_ids:
            option_group = options_lookup.get(option_id)
            if option_group is None:
                raise OrderValidationError(f"Spec option {option_id} not found.")

            option, group = option_group
            if allowed_groups and option.group_id not in allowed_groups:
                raise OrderValidationError(
                    f"Spec option {option_id} not allowed for product {product_id}."
                )
            if option.inventory_status != "in_stock":
                raise OrderValidationError(f"Spec option {option_id} is sold out.")

            modifier = Decimal(option.price_modifier)

            selected_specs.append(
                {
                    "group_id": option.group_id,
                    "group_name": group.name if group else None,
                    "option_id": option.option_id,
                    "option_name": option.name,
                    "price_modifier": float(modifier),
                }
            )
            total_modifier += modifier

        return selected_specs, total_modifier

    @staticmethod
    def _calculate_unit_price(base_price, modifiers: Decimal) -> Decimal:
        base = Decimal(base_price)
        return (base + modifiers).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _ensure_order_access(
        self,
        order: Order,
        actor: User | None,
        guest_session_id: str | None,
    ) -> None:
        if actor:
            if order.user_id != actor.user_id:
                raise OrderOwnershipError("Order does not belong to current user.")
            return

        if not guest_session_id or order.guest_session_id != guest_session_id:
            raise OrderOwnershipError("Guest session does not match order owner.")

    @staticmethod
    def _ensure_order_pending(order: Order) -> None:
        if order.status != "pending_payment":
            raise OrderConflictError("Order is not in pending_payment status.")

    def _build_order_response(
        self,
        order: Order,
        items: list[OrderItem],
    ) -> dict[str, Any]:
        return {
            "order_id": order.order_id,
            "order_number": order.order_number,
            "status": order.status,
            "order_type": order.order_type,
            "total_price": float(order.total_price),
            "created_at": order.created_at.isoformat(),
            "items": [
                {
                    "item_id": item.item_id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "selected_specs": item.selected_specs_json or [],
                }
                for item in items
            ],
        }

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_order_number() -> str:
        now = datetime.now(tz=UTC)
        timestamp = now.strftime("%Y%m%d%H%M%S")
        millis = int(now.microsecond / 1000)
        random_suffix = secrets.token_hex(3).upper()
        return f"{timestamp}{millis:03d}-NA{random_suffix}"
