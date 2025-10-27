from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError, UnmappedInstanceError
from structlog import get_logger

from app.core.settings import Settings
from app.metrics.payments import (
    PAYMENT_CALLBACK_DUPLICATE_TOTAL,
    PAYMENT_CALLBACK_LATENCY_MS,
    PAYMENT_CALLBACK_TOTAL,
)
from app.models.orders import Order, PaymentRecord, PrintJob
from app.schemas.payment import WechatPaymentNotifySchema
from app.workers import enqueue_payment_side_effects, enqueue_print_job

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
            job_to_enqueue: int | None = None
            should_dispatch_side_effects = False
            dispatch_order_id: int | None = None

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
                payment_status_changed = order.payment_status != "paid"
                now_utc = datetime.now(tz=UTC)

                if payment_status_changed:
                    order.payment_status = "paid"
                if status_changed:
                    order.status = "paid"
                    order.updated_at = now_utc
                    dispatch_order_id = order.order_id
                    should_dispatch_side_effects = True
                if order.payment_channel is None:
                    order.payment_channel = payload.channel

                payment_record_stmt = self._build_payment_record_insert(
                    order_id=order.order_id,
                    payload=payload,
                    notify_data=notify_data,
                )
                record_result = await self._session.execute(payment_record_stmt)
                record_inserted = getattr(record_result, "rowcount", 0) > 0
                if not record_inserted:
                    PAYMENT_CALLBACK_DUPLICATE_TOTAL.labels(channel=payload.channel).inc()
                    logger.info(
                        "payment.notification_replayed",
                        order_number=payload.order_number,
                        txn_id=payload.transaction_id,
                    )

                bind = getattr(self._session, "bind", None)
                if bind is not None:
                    dialect_name = getattr(bind.dialect, "name", "")
                else:
                    async with self._session.connection() as conn:
                        dialect_name = conn.dialect.name

                print_job = existing_print_job
                job_candidate: PrintJob | None = None
                job_id_from_existing: int | None = None
                created_new_job = False

                if print_job is None:
                    inserted_job_id: int | None = None
                    try:
                        if dialect_name == "postgresql":
                            insert_stmt = (
                                pg_insert(PrintJob)
                                .values(order_id=order.order_id, status="pending")
                                .on_conflict_do_nothing(index_elements=[PrintJob.order_id])
                                .returning(PrintJob.job_id)
                            )
                        elif dialect_name == "sqlite":
                            insert_stmt = (
                                sqlite_insert(PrintJob)
                                .values(order_id=order.order_id, status="pending")
                                .on_conflict_do_nothing(index_elements=[PrintJob.order_id])
                                .returning(PrintJob.job_id)
                            )
                        else:
                            insert_stmt = (
                                insert(PrintJob)
                                .values(order_id=order.order_id, status="pending")
                                .execution_options(ignore_conflicts=True)
                                .returning(PrintJob.job_id)
                            )
                        insert_result = await self._session.execute(insert_stmt)
                        inserted_job_id = insert_result.scalar_one_or_none()
                    except IntegrityError:
                        inserted_job_id = None

                    if inserted_job_id is not None:
                        print_job = await self._session.get(PrintJob, inserted_job_id)
                        created_new_job = True
                    else:
                        select_job_stmt = select(PrintJob).where(PrintJob.order_id == order.order_id)
                        if dialect_name != "sqlite":
                            select_job_stmt = select_job_stmt.with_for_update()
                        job_result = await self._session.execute(select_job_stmt)
                        print_job = job_result.scalar_one_or_none()
                        if print_job is None and dialect_name == "sqlite":
                            waited = 0.0
                            interval = 0.02
                            max_wait = 5.0
                            while print_job is None and waited < max_wait:
                                await asyncio.sleep(interval)
                                waited += interval
                                job_result = await self._session.execute(
                                    select(PrintJob).where(PrintJob.order_id == order.order_id)
                                )
                                print_job = job_result.scalar_one_or_none()
                        if print_job is None:
                            raise PaymentServiceError("Print job not found after upsert.")

                if created_new_job:
                    print_job.next_try_at = now_utc
                    job_candidate = print_job
                elif print_job.status == "failed":
                    print_job.status = "pending"
                    print_job.next_try_at = now_utc
                    job_candidate = print_job
                elif print_job.status == "pending":
                    if dialect_name != "sqlite":
                        print_job.next_try_at = now_utc
                        job_candidate = print_job
                    else:
                        job_id_from_existing = print_job.job_id
                        sync_session = self._session.sync_session
                        try:
                            sync_session.expunge(print_job)
                        except UnmappedInstanceError:
                            pass
                        if job_id_from_existing is not None:
                            await self._session.execute(
                                update(PrintJob)
                                    .where(PrintJob.job_id == job_id_from_existing)
                                    .values(next_try_at=now_utc)
                            )

                if record_inserted:
                    logger.info(
                        "payment.payment_record_inserted",
                        order_id=order.order_id,
                        record=payload.transaction_id,
                    )
                try:
                    await self._session.flush()
                except StaleDataError as exc:  # pragma: no cover - 乐观锁冲突
                    raise PaymentConflictError("Order state updated concurrently.") from exc

                if job_candidate is not None and job_candidate.job_id is not None:
                    job_to_enqueue = job_candidate.job_id
                elif job_id_from_existing is not None:
                    job_to_enqueue = job_id_from_existing

            if job_to_enqueue is not None:
                try:
                    enqueue_print_job(job_to_enqueue)
                except Exception:
                    logger.exception(
                        "payment.print_enqueue_failed",
                        job_id=job_to_enqueue,
                        order_number=payload.order_number,
                    )

            if should_dispatch_side_effects and dispatch_order_id is not None:
                enqueue_payment_side_effects(dispatch_order_id, source="payment_callback")

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
        bind = self._session.get_bind()
        if bind is not None and getattr(bind.dialect, "name", "") != "sqlite":
            stmt = stmt.with_for_update(of=Order)
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
