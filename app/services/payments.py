from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.orders import Order, PaymentRecord, PrintJob
from app.schemas.payment import WechatPaymentNotifySchema
from app.services.loyalty import LoyaltyService
from app.ws.manager import merchant_notifier


class PaymentServiceError(Exception):
    """支付通知处理异常。"""


class PaymentSignatureError(PaymentServiceError):
    """签名校验失败。"""


class PaymentOrderNotFoundError(PaymentServiceError):
    """找不到对应订单。"""


class PaymentConflictError(PaymentServiceError):
    """通知与订单信息冲突。"""


class PaymentService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def handle_wechat_notification(
        self,
        payload: WechatPaymentNotifySchema,
        *,
        raw_body: bytes,
        signature: str,
    ) -> dict[str, Any]:
        self._verify_signature(raw_body, signature)

        notify_data = json.loads(payload.model_dump_json())
        status_changed = False

        if self._session.in_transaction():
            transaction_ctx = self._session.begin_nested()
        else:
            transaction_ctx = self._session.begin()

        async with transaction_ctx:
            order = await self._load_order_for_update(payload.order_number)
            if order is None:
                raise PaymentOrderNotFoundError("Order not found for payment notification.")

            self._ensure_amount_matches(order, payload.amount, payload.currency)

            payment_record = await self._session.scalar(
                select(PaymentRecord).where(PaymentRecord.txn_id == payload.transaction_id)
            )
            if payment_record is None:
                payment_record = PaymentRecord(
                    record_type="payment",
                    channel=payload.channel,
                    currency=payload.currency,
                    amount=Decimal(payload.amount),
                    txn_id=payload.transaction_id,
                    out_trade_no=payload.order_number,
                    matched_order_id=order.order_id,
                    match_status="auto_matched",
                    paid_at=payload.paid_at,
                    raw_notification_json=notify_data.get("raw_notification") or notify_data,
                )
                self._session.add(payment_record)

            if order.status != "paid":
                order.status = "paid"
                order.updated_at = datetime.now(tz=UTC)
                status_changed = True

            await self._ensure_print_job(order)
            await self._session.flush()
            await LoyaltyService(self._session).award_on_payment(order)

        if status_changed:
            await self._session.refresh(order)
            await merchant_notifier.broadcast(self._build_broadcast_payload(order))

        return {"status": "SUCCESS"}

    async def _load_order_for_update(self, order_number: str) -> Order | None:
        stmt = select(Order).where(Order.order_number == order_number)
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        return await self._session.scalar(stmt)

    def _verify_signature(self, raw_body: bytes, signature: str) -> None:
        expected = hmac.new(
            self._settings.secret_key.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not signature or signature.lower() != expected.lower():
            raise PaymentSignatureError("Invalid signature.")

    @staticmethod
    def _ensure_amount_matches(order: Order, amount: float, currency: str) -> None:
        order_total = Decimal(order.total_price)
        incoming = Decimal(str(amount))
        if currency != "CNY":
            raise PaymentConflictError("Unsupported currency.")
        if order_total != incoming:
            raise PaymentConflictError("Payment amount mismatches order total.")

    async def _ensure_print_job(self, order: Order) -> None:
        result = await self._session.execute(
            select(PrintJob).where(PrintJob.order_id == order.order_id)
        )
        job = result.scalar_one_or_none()
        if job is not None:
            return
        self._session.add(PrintJob(order_id=order.order_id))

    @staticmethod
    def _build_broadcast_payload(order: Order) -> dict[str, Any]:
        paid_at = order.updated_at or datetime.now(tz=UTC)
        return {
            "type": "order.paid",
            "order": {
                "order_id": order.order_id,
                "order_number": order.order_number,
                "total_price": float(order.total_price),
                "status": order.status,
                "paid_at": paid_at.isoformat(),
            },
        }
