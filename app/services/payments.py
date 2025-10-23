from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any
from types import SimpleNamespace

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from structlog import get_logger

from app.core.settings import Settings
from app.metrics.payments import (
    PAYMENT_CALLBACK_LATENCY_MS,
    PAYMENT_CALLBACK_TOTAL,
)
from app.models.orders import Order, PaymentRecord, PrintJob
from app.schemas.payment import WechatPaymentNotifySchema
from app.services.loyalty import LoyaltyService
from app.workers import enqueue_print_job
from app.ws.manager import merchant_notifier

logger = get_logger(__name__)


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
        started_at = perf_counter()
        result_label = "success"

        try:
            logger.info(
                "payment.notification_received",
                extra={
                    "order_number": payload.order_number,
                    "transaction_id": payload.transaction_id,
                    "amount": payload.amount,
                    "channel": payload.channel,
                },
            )

            self._verify_signature(raw_body, signature)

            notify_data = json.loads(payload.model_dump_json())
            status_changed = False
            broadcast_payload: dict[str, Any] | None = None
            job_to_enqueue: int | None = None

            if self._session.in_transaction():
                transaction_ctx = self._session.begin_nested()
            else:
                transaction_ctx = self._session.begin()

            print_job: PrintJob | None = None

            async with transaction_ctx:
                logger.debug(
                    "payment.loading_order",
                    extra={"order_number": payload.order_number},
                )
                order_row = await self._load_order_with_print_job(payload.order_number)
                if order_row is None:
                    logger.error(
                        "payment.order_not_found",
                        extra={
                            "order_number": payload.order_number,
                            "transaction_id": payload.transaction_id,
                        },
                    )
                    raise PaymentOrderNotFoundError("Order not found for payment notification.")

                order, existing_print_job = order_row

                self._ensure_amount_matches(order, payload.amount, payload.currency)

                status_changed = order.status != "paid"
                now_utc = datetime.now(tz=UTC)

                update_values: dict[str, Any] = {"payment_status": "paid"}
                if status_changed:
                    update_values["status"] = "paid"
                    update_values["updated_at"] = now_utc
                if order.payment_channel is None:
                    update_values["payment_channel"] = payload.channel

                updated_order_row = await self._session.execute(
                    update(Order)
                    .where(Order.order_id == order.order_id)
                    .values(**update_values)
                    .returning(
                        Order.order_id,
                        Order.order_number,
                        Order.total_price,
                        Order.status,
                        Order.payment_status,
                        Order.payment_channel,
                        Order.updated_at,
                    )
                )
                updated_order = updated_order_row.one()

                payment_record_stmt = self._build_payment_record_insert(
                    order_id=order.order_id,
                    payload=payload,
                    notify_data=notify_data,
                )
                record_result = await self._session.execute(payment_record_stmt)
                record_inserted = getattr(record_result, "rowcount", 0) > 0
                if not record_inserted:
                    logger.info(
                        "payment.notification_replayed",
                        order_number=payload.order_number,
                        txn_id=payload.transaction_id,
                    )

                print_job = existing_print_job
                job_candidate: PrintJob | None = None
                if print_job is None:
                    print_job = PrintJob(order_id=order.order_id, status="pending")
                    self._session.add(print_job)
                    job_candidate = print_job
                elif print_job.status in {"pending", "failed"}:
                    print_job.status = "pending"
                    print_job.next_try_at = now_utc
                    job_candidate = print_job

                if status_changed:
                    broadcast_payload = self._build_broadcast_payload(
                        SimpleNamespace(
                            order_id=updated_order.order_id,
                            order_number=updated_order.order_number,
                            total_price=updated_order.total_price,
                            status=updated_order.status,
                            updated_at=updated_order.updated_at,
                        )
                    )

                if record_inserted:
                    await LoyaltyService(self._session, self._settings).award_on_payment(
                        order,
                        skip_duplicate_check=True,
                    )
                await self._session.flush()

                if job_candidate is not None and job_candidate.job_id is not None:
                    job_to_enqueue = job_candidate.job_id

            if status_changed and broadcast_payload is not None:
                try:
                    await merchant_notifier.broadcast(broadcast_payload)
                except Exception:
                    logger.exception(
                        "payment.broadcast_failed",
                        order_number=payload.order_number,
                        txn_id=payload.transaction_id,
                    )

            if job_to_enqueue is not None:
                try:
                    enqueue_print_job(job_to_enqueue)
                except Exception:
                    logger.exception(
                        "payment.print_enqueue_failed",
                        job_id=job_to_enqueue,
                        order_number=payload.order_number,
                    )

            return {"status": "SUCCESS"}
        except PaymentSignatureError:
            result_label = "signature_error"
            raise
        except PaymentOrderNotFoundError:
            result_label = "order_not_found"
            raise
        except PaymentConflictError:
            result_label = "conflict"
            raise
        except PaymentServiceError:
            result_label = "service_error"
            raise
        except Exception:
            result_label = "unexpected_error"
            raise
        finally:
            elapsed_ms = (perf_counter() - started_at) * 1000
            PAYMENT_CALLBACK_LATENCY_MS.observe(elapsed_ms)
            PAYMENT_CALLBACK_TOTAL.labels(result=result_label).inc()

    async def _load_order_with_print_job(
        self, order_number: str
    ) -> tuple[Order, PrintJob | None] | None:
        stmt = (
            select(Order, PrintJob)
            .outerjoin(PrintJob, PrintJob.order_id == Order.order_id)
            .where(Order.order_number == order_number)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

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

    def _build_payment_record_insert(
        self,
        *,
        order_id: int,
        payload: WechatPaymentNotifySchema,
        notify_data: dict[str, Any],
    ):
        values = {
            "record_type": "payment",
            "channel": payload.channel,
            "currency": payload.currency,
            "amount": Decimal(str(payload.amount)),
            "txn_id": payload.transaction_id,
            "out_trade_no": payload.order_number,
            "matched_order_id": order_id,
            "match_status": "auto_matched",
            "paid_at": payload.paid_at,
            "raw_notification_json": notify_data.get("raw_notification") or notify_data,
        }

        bind = self._session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""

        if dialect_name == "postgresql":
            return pg_insert(PaymentRecord).values(**values).on_conflict_do_nothing(
                index_elements=[PaymentRecord.txn_id]
            )
        if dialect_name == "sqlite":
            return sqlite_insert(PaymentRecord).values(**values).on_conflict_do_nothing(
                index_elements=[PaymentRecord.txn_id]
            )
        return insert(PaymentRecord).values(**values)

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
