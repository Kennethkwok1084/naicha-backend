from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.models.orders import Order, PaymentRecord

logger = get_logger(__name__)


@dataclass(slots=True)
class ReconciliationResult:
    range_start: datetime
    range_end: datetime
    orders_without_payment: list[dict]
    orders_without_refund: list[dict]
    unmatched_payments: list[dict]

    @property
    def total_differences(self) -> int:
        return (
            len(self.orders_without_payment)
            + len(self.orders_without_refund)
            + len(self.unmatched_payments)
        )


class ReconciliationService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._tz = ZoneInfo("Asia/Shanghai")

    async def run_daily(
        self,
        *,
        reference: datetime | None = None,
        csv_enabled: bool | None = None,
    ) -> ReconciliationResult:
        """Reconcile the previous local day of orders and payment records."""

        effective_reference = reference or datetime.now(tz=UTC)
        local_reference = effective_reference.astimezone(self._tz)
        target_day = local_reference.date() - timedelta(days=1)

        range_start_local = datetime.combine(target_day, datetime.min.time(), tzinfo=self._tz)
        range_end_local = range_start_local + timedelta(days=1)

        range_start = range_start_local.astimezone(UTC)
        range_end = range_end_local.astimezone(UTC)

        orders = await self._fetch_orders(range_start, range_end)
        payments = await self._fetch_payments(range_start, range_end)
        refunds = await self._fetch_refunds(range_start, range_end)

        matched_order_ids = {
            record.matched_order_id for record in payments if record.matched_order_id
        }
        matched_refund_order_ids = {
            record.matched_order_id for record in refunds if record.matched_order_id
        }

        orders_missing_payment = [
            self._serialize_order(order)
            for order in orders
            if order.payment_status == "paid" and order.order_id not in matched_order_ids
        ]

        orders_missing_refund = [
            self._serialize_order(order)
            for order in orders
            if order.status == "refunded" and order.order_id not in matched_refund_order_ids
        ]

        unmatched_payments = [
            self._serialize_payment(record)
            for record in payments
            if not record.matched_order_id or record.match_status in {"unmatched", "failed"}
        ]

        result = ReconciliationResult(
            range_start=range_start,
            range_end=range_end,
            orders_without_payment=orders_missing_payment,
            orders_without_refund=orders_missing_refund,
            unmatched_payments=unmatched_payments,
        )

        logger.info(
            "reconciliation.summary",
            range_start=range_start.isoformat(),
            range_end=range_end.isoformat(),
            orders_without_payment=len(orders_missing_payment),
            orders_without_refund=len(orders_missing_refund),
            unmatched_payments=len(unmatched_payments),
        )

        csv_requested = (
            csv_enabled if csv_enabled is not None else self._settings.reconciliation_csv_enabled
        )

        if csv_requested:
            self._export_csv(result)

        return result

    async def _fetch_orders(self, start: datetime, end: datetime) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.created_at >= start, Order.created_at < end)
            .where(
                or_(
                    Order.payment_status.in_(["paid", "refunded"]),
                    Order.status == "refunded",
                )
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_payments(self, start: datetime, end: datetime) -> list[PaymentRecord]:
        stmt = (
            select(PaymentRecord)
            .where(PaymentRecord.record_type == "payment")
            .where(PaymentRecord.paid_at >= start, PaymentRecord.paid_at < end)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_refunds(self, start: datetime, end: datetime) -> list[PaymentRecord]:
        stmt = (
            select(PaymentRecord)
            .where(PaymentRecord.record_type == "refund")
            .where(PaymentRecord.paid_at >= start, PaymentRecord.paid_at < end)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _serialize_order(self, order: Order) -> dict:
        return {
            "order_id": order.order_id,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": order.payment_status,
            "total_price": float(order.total_price),
        }

    def _serialize_payment(self, record: PaymentRecord) -> dict:
        return {
            "payment_record_id": record.pay_id,
            "amount": float(record.amount),
            "record_type": record.record_type,
            "match_status": record.match_status,
            "matched_order_id": record.matched_order_id,
        }

    def _export_csv(self, result: ReconciliationResult) -> None:
        if not self._settings.reconciliation_report_dir:
            logger.warning("reconciliation.csv_skipped", reason="report_dir_missing")
            return

        output_dir = Path(self._settings.reconciliation_report_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = (
            f"reconciliation_{result.range_start.astimezone(self._tz).date().isoformat()}.csv"
        )
        path = output_dir / filename

        rows = list(self._compose_csv_rows(result))
        with path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=[
                    "category",
                    "order_id",
                    "order_number",
                    "status",
                    "payment_status",
                    "payment_record_id",
                    "amount",
                    "match_status",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        logger.info("reconciliation.csv_written", path=str(path), rows=len(rows))

    def _compose_csv_rows(self, result: ReconciliationResult) -> Iterable[dict[str, object]]:
        for item in result.orders_without_payment:
            yield {
                "category": "orders_without_payment",
                "order_id": item["order_id"],
                "order_number": item["order_number"],
                "status": item["status"],
                "payment_status": item["payment_status"],
                "payment_record_id": None,
                "amount": None,
                "match_status": None,
            }
        for item in result.orders_without_refund:
            yield {
                "category": "orders_without_refund",
                "order_id": item["order_id"],
                "order_number": item["order_number"],
                "status": item["status"],
                "payment_status": item["payment_status"],
                "payment_record_id": None,
                "amount": None,
                "match_status": None,
            }
        for item in result.unmatched_payments:
            yield {
                "category": "unmatched_payments",
                "order_id": item["matched_order_id"],
                "order_number": None,
                "status": None,
                "payment_status": None,
                "payment_record_id": item["payment_record_id"],
                "amount": item["amount"],
                "match_status": item["match_status"],
            }


__all__ = ["ReconciliationResult", "ReconciliationService"]
