from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.metrics.inventory import (
    INVENTORY_CURRENT_STOCK,
    INVENTORY_DEDUCTION_TOTAL,
    INVENTORY_OVERSELL_TOTAL,
)
from app.metrics.orders import (
    ORDER_AUTO_CANCEL_DELAY_SECONDS,
    ORDER_AUTO_CANCEL_TOTAL,
    ORDER_CREATE_TOTAL,
)
from app.models.accounts import User
from app.models.catalog import Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.orders import AuditLog, IdempotencyKey, Order, OrderItem
from app.schemas.order import (
    OrderCreateRequestSchema,
    OrderPaymentJsapiRequestSchema,
    OrderPaymentNativeRequestSchema,
)
from app.services.inventory import InventoryService
from app.services.reservations import ReservationService, ReservationValidationError


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
        post_create: Callable[[Order, list[OrderItem]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        if not idempotency_key.strip():
            raise OrderValidationError("Idempotency-Key header is required.")

        actor_guest_session = payload.guest_session_id
        if user is None and not actor_guest_session:
            raise OrderValidationError("guest_session_id is required for anonymous checkout.")
        if payload.order_type == "delivery" and payload.address is None:
            raise OrderValidationError("Delivery order requires address.")

        payload_dict = payload.model_dump(mode="json")
        payload_hash = self._hash_payload(payload_dict)

        started_transaction = False
        try:
            if not self._session.in_transaction():
                await self._session.begin()
                started_transaction = True

            result = await self._create_order_internal(
                payload=payload,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                user=user,
                guest_session_id=actor_guest_session,
                post_create=post_create,
            )

            if started_transaction:
                await self._session.commit()
        except OrderServiceError:
            if started_transaction and self._session.in_transaction():
                await self._session.rollback()
            ORDER_CREATE_TOTAL.labels(result="service_error").inc()
            raise
        except Exception:
            if started_transaction and self._session.in_transaction():
                await self._session.rollback()
            ORDER_CREATE_TOTAL.labels(result="unexpected_error").inc()
            raise
        ORDER_CREATE_TOTAL.labels(result="success").inc()
        return result

    async def _create_order_internal(
        self,
        *,
        payload: OrderCreateRequestSchema,
        idempotency_key: str,
        payload_hash: str,
        user: User | None,
        guest_session_id: str | None,
        post_create: Callable[[Order, list[OrderItem]], Awaitable[None]] | None,
    ) -> dict[str, Any]:
        if guest_session_id:
            await self._validate_guest_session(guest_session_id)

        idempotency_record, cached_response = await self._ensure_idempotency(
            idempotency_key, payload_hash
        )
        if cached_response is not None:
            return cached_response

        reservation_plan = None
        if payload.scheduled_at is not None:
            if payload.order_type != "pickup":
                raise OrderValidationError("目前仅支持到店自提预约。")
            reservation_service = ReservationService(self._session, self._settings)
            try:
                reservation_plan = await reservation_service.plan(payload.scheduled_at)
            except ReservationValidationError as exc:
                raise OrderValidationError(str(exc)) from exc

        items_payload = payload.items
        products, product_groups = await self._load_products_with_groups(items_payload)
        specs_lookup = await self._load_spec_options(items_payload)

        db_items_payload: list[dict[str, Any]] = []
        response_items_base: list[dict[str, Any]] = []
        total_price = Decimal("0.00")

        for item in items_payload:
            product = products.get(item.product_id)
            if product is None:
                raise OrderValidationError(f"Product {item.product_id} not found.")
            if product.status != "active":
                raise OrderValidationError(f"Product {item.product_id} is inactive.")
            if product.inventory_status != "in_stock":
                raise OrderValidationError(f"Product {item.product_id} is sold out.")
            remaining_stock = getattr(product, "stock_quantity", None)
            if remaining_stock is not None:
                if remaining_stock < item.quantity:
                    INVENTORY_DEDUCTION_TOTAL.labels(result="insufficient").inc()
                    INVENTORY_OVERSELL_TOTAL.labels(product_id=str(product.product_id)).inc()
                    raise OrderValidationError(f"Product {item.product_id} is sold out.")
                product.stock_quantity = remaining_stock - item.quantity
                INVENTORY_DEDUCTION_TOTAL.labels(result="success").inc()
                INVENTORY_CURRENT_STOCK.labels(product_id=str(product.product_id)).set(
                    product.stock_quantity
                )
                if product.stock_quantity == 0 and product.inventory_status != "sold_out":
                    product.inventory_status = "sold_out"

            allowed_groups = product_groups.get(item.product_id, set())
            selected_specs, modifiers_total = self._pick_spec_options(
                item.spec_option_ids,
                specs_lookup,
                allowed_groups,
                item.product_id,
            )

            unit_price = self._calculate_unit_price(product.base_price, modifiers_total)
            total_price += unit_price * item.quantity

            db_items_payload.append(
                {
                    "product_id": product.product_id,
                    "product_name": product.name,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "selected_specs_json": selected_specs,
                }
            )
            response_items_base.append(
                {
                    "product_id": product.product_id,
                    "product_name": product.name,
                    "quantity": item.quantity,
                    "unit_price": float(unit_price),
                    "selected_specs": selected_specs,
                }
            )

        order_values = await self._build_order_entity(
            payload,
            user,
            guest_session_id,
            reservation_plan=reservation_plan,
        )
        order_values["total_price"] = total_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        order_stmt = (
            insert(Order)
            .values(order_values)
            .returning(
                Order.order_id,
                Order.order_number,
                Order.status,
                Order.order_type,
                Order.total_price,
                Order.payment_status,
                Order.payment_channel,
                Order.is_scheduled,
                Order.scheduled_at,
                Order.reminder_sent_at,
                Order.created_at,
            )
        )
        order_result = await self._session.execute(order_stmt)
        order_row = order_result.one()
        order_id = order_row.order_id

        for payload_item in db_items_payload:
            payload_item["order_id"] = order_id

        items_stmt = (
            insert(OrderItem)
            .returning(
                OrderItem.item_id,
                OrderItem.product_id,
                OrderItem.product_name,
                OrderItem.quantity,
                OrderItem.unit_price,
                OrderItem.selected_specs_json,
            )
        )
        items_result = await self._session.execute(items_stmt, db_items_payload)
        inserted_items = items_result.fetchall()

        response_items: list[dict[str, Any]] = []
        for base, row in zip(response_items_base, inserted_items, strict=True):
            response_items.append(
                {
                    "item_id": row.item_id,
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "quantity": row.quantity,
                    "unit_price": float(row.unit_price),
                    "selected_specs": row.selected_specs_json or base["selected_specs"],
                }
            )

        if post_create is not None:
            order_entity = await self._session.get(Order, order_id)
            if order_entity is None:
                raise OrderServiceError("订单创建后未能加载订单数据。")

            items_entities_result = await self._session.execute(
                select(OrderItem).where(OrderItem.order_id == order_id)
            )
            order_items_entities = list(items_entities_result.scalars().all())

            await post_create(order_entity, order_items_entities)
            await self._session.flush()
            await self._session.refresh(order_entity)

            refreshed_items_result = await self._session.execute(
                select(OrderItem).where(OrderItem.order_id == order_id)
            )
            order_items_entities = list(refreshed_items_result.scalars().all())
            response_payload = self._build_order_response(order_entity, order_items_entities)
        else:
            response_payload = self._build_order_response_from_row(order_row, response_items)
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
        expires_at = datetime.now(tz=UTC) + timedelta(hours=self.IDEMPOTENCY_TTL_HOURS)
        bind = getattr(self._session, "bind", None)
        if bind is not None:
            dialect_name = getattr(bind.dialect, "name", "")
        else:
            async with self._session.connection() as conn:
                dialect_name = conn.dialect.name

        insert_payload = {
            "idempotency_key": key,
            "scope": self.CREATE_SCOPE,
            "request_hash": payload_hash,
            "expire_at": expires_at,
        }

        if dialect_name == "postgresql":
            insert_stmt = (
                pg_insert(IdempotencyKey)
                .values(insert_payload)
                .on_conflict_do_nothing(index_elements=[IdempotencyKey.idempotency_key])
            )
        elif dialect_name == "sqlite":
            insert_stmt = (
                sqlite_insert(IdempotencyKey)
                .values(insert_payload)
                .on_conflict_do_nothing(index_elements=[IdempotencyKey.idempotency_key])
            )
        else:
            insert_stmt = insert(IdempotencyKey).values(insert_payload).execution_options(
                ignore_conflicts=True
            )

        insert_result = await self._session.execute(insert_stmt)
        inserted_here = bool(getattr(insert_result, "rowcount", 0))

        select_stmt = select(IdempotencyKey).where(IdempotencyKey.idempotency_key == key)
        if dialect_name != "sqlite":
            select_stmt = select_stmt.with_for_update()

        result = await self._session.execute(select_stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise OrderServiceError("未能加载幂等键记录。")

        if record.scope != self.CREATE_SCOPE:
            raise OrderConflictError("Idempotency key scope mismatch.")
        if record.request_hash and record.request_hash != payload_hash:
            raise OrderConflictError("Idempotency key reused with different payload.")

        if not inserted_here and dialect_name == "sqlite" and record.response_snapshot is None:
            waited = 0.0
            interval = 0.02
            max_wait = 5.0
            while record.response_snapshot is None and waited < max_wait:
                await asyncio.sleep(interval)
                waited += interval
                await self._session.refresh(record)
            if record.response_snapshot is None:
                raise OrderConflictError("Idempotency key is currently being processed.")

        record.scope = self.CREATE_SCOPE
        if record.request_hash is None:
            record.request_hash = payload_hash
        record.expire_at = expires_at

        if record.response_snapshot is not None:
            return record, record.response_snapshot
        return record, None

    async def _validate_guest_session(self, guest_session_id: str) -> None:
        record = await self._session.get(IdempotencyKey, guest_session_id)
        if not record or record.scope != self.GUEST_SCOPE:
            raise OrderValidationError("Guest session is invalid.")
        if record.expire_at and record.expire_at < datetime.now(tz=UTC):
            raise OrderValidationError("Guest session has expired.")

    async def _load_products_with_groups(
        self, items
    ) -> tuple[dict[int, Product], dict[int, set[int]]]:
        """
        批量加载商品及允许的规格组。

        通过一次查询拿到商品和映射表，减少多次 round-trip。
        """
        product_ids = {item.product_id for item in items}
        if not product_ids:
            return {}, {}

        products_stmt = (
            select(Product)
            .where(Product.product_id.in_(product_ids))
            .with_for_update(of=Product)
        )
        products_result = await self._session.execute(products_stmt)
        products_list = list(products_result.scalars().all())

        products: dict[int, Product] = {product.product_id: product for product in products_list}
        product_groups: dict[int, set[int]] = {}

        if products:
            mappings_stmt = select(ProductSpecMapping).where(
                ProductSpecMapping.product_id.in_(product_ids)
            )
            mappings_result = await self._session.execute(mappings_stmt)
            for mapping in mappings_result.scalars().all():
                product_groups.setdefault(mapping.product_id, set()).add(mapping.group_id)
        return products, product_groups

    async def _load_spec_options(self, items) -> dict[int, tuple[SpecOption, SpecGroup | None]]:
        option_ids = {option_id for item in items for option_id in item.spec_option_ids}
        if not option_ids:
            return {}

        options_stmt = (
            select(SpecOption)
            .where(SpecOption.option_id.in_(option_ids))
            .with_for_update(of=SpecOption)
        )
        options_result = await self._session.execute(options_stmt)
        options_list = list(options_result.scalars().all())

        lookup: dict[int, tuple[SpecOption, SpecGroup | None]] = {}
        if not options_list:
            return lookup

        group_ids = {option.group_id for option in options_list if option.group_id is not None}
        groups: dict[int, SpecGroup] = {}
        if group_ids:
            groups_stmt = select(SpecGroup).where(SpecGroup.group_id.in_(group_ids))
            groups_result = await self._session.execute(groups_stmt)
            groups = {group.group_id: group for group in groups_result.scalars().all()}

        for option in options_list:
            lookup[option.option_id] = (option, groups.get(option.group_id))
        return lookup

    async def _build_order_entity(
        self,
        payload: OrderCreateRequestSchema,
        user: User | None,
        guest_session_id: str | None,
        *,
        reservation_plan,
    ) -> dict[str, Any]:
        order_number = self._generate_order_number()
        address_json = payload.address.model_dump() if payload.address else None
        scheduled_at = reservation_plan.scheduled_at_utc if reservation_plan else None
        reservation_slot_id = reservation_plan.slot_id if reservation_plan else None

        return {
            "order_number": order_number,
            "user_id": user.user_id if user else None,
            "guest_session_id": None if user else guest_session_id,
            "total_price": Decimal("0.00"),
            "notes": payload.notes,
            "status": "pending_payment",
            "order_type": payload.order_type,
            "address_json": address_json,
            "payment_status": "pending",
            "source": "user",
            "payment_channel": None,
            "created_by_admin_id": None,
            "is_scheduled": bool(reservation_plan),
            "scheduled_at": scheduled_at,
            "reservation_slot_id": reservation_slot_id,
        }

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

    async def cancel_pending_order(
        self,
        order_id: int,
        *,
        reason: str,
        source: str = "celery",
    ) -> bool:
        bind = getattr(self._session, "bind", None)
        if bind is not None:
            dialect_name = getattr(bind.dialect, "name", "")
        else:
            async with self._session.connection() as conn:
                dialect_name = conn.dialect.name

        stmt = select(Order).where(Order.order_id == order_id)
        if dialect_name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            ORDER_AUTO_CANCEL_TOTAL.labels(source=source, result="not_found").inc()
            return False
        if order.status != "pending_payment" or order.payment_status != "pending":
            ORDER_AUTO_CANCEL_TOTAL.labels(source=source, result="not_pending").inc()
            return False

        items_result = await self._session.execute(
            select(OrderItem).where(OrderItem.order_id == order.order_id)
        )
        items = list(items_result.scalars().all())

        inventory_service = InventoryService(self._session, self._settings)
        inventory_changes = await inventory_service.restore_from_order_items(
            items,
            dialect_name=dialect_name,
        )

        now = datetime.now(tz=UTC)
        previous_status = order.status
        previous_payment_status = order.payment_status
        order.status = "cancelled"
        order.updated_at = now
        reservation_slot_id = order.reservation_slot_id

        if inventory_changes:
            summary = inventory_changes
        else:
            summary = None

        audit = AuditLog(
            actor_type="system",
            actor_admin_id=None,
            actor_user_id=None,
            action="order.auto_cancel",
            target_table="orders",
            target_id=str(order.order_id),
            before_json={
                "status": previous_status,
                "payment_status": previous_payment_status,
            },
            after_json={
                "status": order.status,
                "payment_status": order.payment_status,
                "reason": reason,
                "inventory_restored": summary,
            },
            ip=None,
            user_agent=None,
        )
        self._session.add(audit)

        await self._session.flush()
        created_at = order.created_at or now
        if created_at.tzinfo is None or created_at.tzinfo.utcoffset(created_at) is None:
            created_at = created_at.replace(tzinfo=UTC)
        delay_seconds = max((now - created_at).total_seconds(), 0.0)
        ORDER_AUTO_CANCEL_TOTAL.labels(source=source, result="success").inc()
        ORDER_AUTO_CANCEL_DELAY_SECONDS.labels(source=source).observe(delay_seconds)

        if reservation_slot_id:
            reservation_service = ReservationService(self._session, self._settings)
            await reservation_service.release_slot(reservation_slot_id)
            order.reservation_slot_id = None
            order.is_scheduled = False
            await self._session.flush()

        return True

    async def cancel_stale_pending_orders(
        self,
        cutoff: datetime,
        *,
        limit: int = 50,
        reason: str = "auto_cancel.pending_timeout",
        source: str = "celery",
    ) -> list[int]:
        stmt = (
            select(Order.order_id)
            .where(
                Order.status == "pending_payment",
                Order.payment_status == "pending",
                Order.created_at <= cutoff,
            )
            .order_by(Order.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        order_ids = [row[0] for row in result.fetchall()]

        cancelled: list[int] = []
        for target_id in order_ids:
            success = await self.cancel_pending_order(target_id, reason=reason, source=source)
            if success:
                cancelled.append(target_id)

        return cancelled

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
            "created_at": self._serialize_datetime(order.created_at),
            "is_scheduled": order.is_scheduled,
            "scheduled_at": self._serialize_datetime(order.scheduled_at),
            "reminder_sent_at": self._serialize_datetime(order.reminder_sent_at),
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

    def _build_order_response_from_row(
        self,
        order_row,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "order_id": order_row.order_id,
            "order_number": order_row.order_number,
            "status": order_row.status,
            "order_type": order_row.order_type,
            "total_price": float(order_row.total_price),
            "created_at": self._serialize_datetime(order_row.created_at),
            "is_scheduled": bool(order_row.is_scheduled),
            "scheduled_at": self._serialize_datetime(order_row.scheduled_at),
            "reminder_sent_at": self._serialize_datetime(order_row.reminder_sent_at),
            "items": items,
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

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
