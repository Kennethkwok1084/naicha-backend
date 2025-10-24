from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.core.settings import Settings
from app.metrics.payments import PAYMENT_MATCH_ATTEMPT_TOTAL
from app.models.accounts import Admin
from app.models.orders import AuditLog, Order, PaymentRecord, PrintJob
from app.schemas import (
    AdminPaymentMatchCandidateSchema,
    AdminPaymentMatchRequestSchema,
    AdminPaymentMatchResponseSchema,
)
from app.services.loyalty import LoyaltyService
from app.utils.distributed_lock import distributed_lock
from app.workers import enqueue_print_job
from app.ws.manager import merchant_notifier


class PaymentMatchError(Exception):
    """静态码匹配异常基类。"""


class PaymentMatchNotFoundError(PaymentMatchError):
    """未找到匹配候选。"""


class PaymentMatchAmbiguousError(PaymentMatchError):
    """存在多个候选,需要人工确认。"""

    def __init__(self, candidates: list[AdminPaymentMatchCandidateSchema]):
        super().__init__("Multiple candidate orders found.")
        self.candidates = candidates


class PaymentMatchConflictError(PaymentMatchError):
    """输入或当前状态冲突。"""


class PaymentMatchService:
    """处理管理员静态码支付匹配流程。"""

    MATCH_SCORE_UNIQUE = Decimal("1.0")
    MATCH_SCORE_MANUAL = Decimal("0.0")

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._logger = get_logger(__name__)

    async def match_payment(
        self,
        *,
        admin: Admin,
        payload: AdminPaymentMatchRequestSchema,
        ip: str | None,
        user_agent: str | None,
    ) -> AdminPaymentMatchResponseSchema:
        """执行静态码支付匹配,使用分布式锁防止并发冲突。
        
        锁策略:
        1. 若提供 transaction_id,锁定该交易记录 (防止重复匹配同一笔支付)
        2. 若未提供 transaction_id 但有 qr_session_id,锁定该 QR 会话 (防止同一静态码并发匹配)
        3. 否则锁定 (amount, time_window) 组合 (防止金额+时间窗口冲突)
        
        失败降级: Redis 不可用时记录错误日志并抛出 503,拒绝处理以保证数据一致性。
        """
        paid_at = self._ensure_timezone(payload.paid_at)
        amount = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
        window_minutes = max(self._settings.static_match_time_window_min, 1)
        window_start = paid_at - timedelta(minutes=window_minutes)
        window_end = paid_at + timedelta(minutes=window_minutes)

        # 构建分布式锁键 (优先级: transaction_id > qr_session_id > amount+time)
        if payload.transaction_id:
            lock_key = f"payment_match:txn:{payload.transaction_id}"
        elif payload.qr_session_id:
            lock_key = f"payment_match:qr:{payload.qr_session_id}"
        else:
            # 使用金额和时间窗口哈希作为锁键 (降低碰撞概率)
            lock_suffix = f"{amount}_{int(paid_at.timestamp())}"
            lock_key = f"payment_match:fuzzy:{lock_suffix}"

        async with distributed_lock(lock_key, timeout=10, blocking=False) as acquired:
            if not acquired:
                # 未获取到锁,说明有并发请求正在处理同一资源,拒绝服务
                self._logger.warning(
                    "payment_match.lock_acquisition_failed",
                    lock_key=lock_key,
                    transaction_id=payload.transaction_id,
                    qr_session_id=payload.qr_session_id,
                )
                PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="lock_failed").inc()
                raise PaymentMatchConflictError(
                    "Concurrent match request detected. Please retry after a few seconds."
                )

            return await self._do_match_payment(
                admin=admin,
                payload=payload,
                amount=amount,
                paid_at=paid_at,
                window_start=window_start,
                window_end=window_end,
                ip=ip,
                user_agent=user_agent,
            )

    async def _do_match_payment(
        self,
        *,
        admin: Admin,
        payload: AdminPaymentMatchRequestSchema,
        amount: Decimal,
        paid_at: datetime,
        window_start: datetime,
        window_end: datetime,
        ip: str | None,
        user_agent: str | None,
    ) -> AdminPaymentMatchResponseSchema:
        """执行实际的匹配逻辑 (已在分布式锁保护下)。"""

        broadcast_payload: dict[str, Any] | None = None
        job_to_enqueue: int | None = None

        if self._session.in_transaction():
            transaction_ctx = self._session.begin_nested()
        else:
            transaction_ctx = self._session.begin()

        async with transaction_ctx:
            payment_record = await self._acquire_payment_record(
                payload=payload,
                amount=amount,
                window_start=window_start,
                window_end=window_end,
            )

            if payload.force_order_id is not None:
                order = await self._load_order_by_id(payload.force_order_id)
                match_status = "manual_matched"
                match_score = self.MATCH_SCORE_MANUAL
            else:
                candidates = await self._find_candidate_orders(
                    amount=amount,
                    window_start=window_start,
                    window_end=window_end,
                )
                if not candidates:
                    PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="not_found").inc()
                    raise PaymentMatchNotFoundError("No pending orders matched payment amount.")
                if len(candidates) > 1:
                    PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="ambiguous").inc()
                    raise PaymentMatchAmbiguousError(
                        [self._build_candidate_schema(order, paid_at) for order in candidates]
                    )
                order = candidates[0]
                match_status = "auto_matched"
                match_score = self.MATCH_SCORE_UNIQUE

            if Decimal(str(order.total_price)).quantize(Decimal("0.01")) != amount:
                PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="conflict").inc()
                raise PaymentMatchConflictError("Payment amount mismatches order total.")
            if order.payment_status == "paid":
                PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="conflict").inc()
                raise PaymentMatchConflictError("Order is already marked as paid.")

            payment_record.match_status = match_status
            payment_record.matched_order_id = order.order_id
            payment_record.matched_by_admin_id = admin.admin_id
            payment_record.match_confidence = match_score
            payment_record.channel = payment_record.channel or "static_qr"
            if payload.qr_session_id:
                payment_record.qr_session_id = payload.qr_session_id
            if payload.trace_id:
                payload_meta = payment_record.raw_notification_json or {}
                payload_meta.setdefault("tags", []).append("admin_match")
                payload_meta["trace_id"] = payload.trace_id
                payment_record.raw_notification_json = payload_meta

            order.status = "paid"
            order.payment_status = "paid"
            order.payment_channel = "static_qr"
            order.updated_at = datetime.now(tz=UTC)

            print_job = await self._ensure_print_job(order)
            if print_job is not None and print_job.status in {"pending", "failed"}:
                print_job.status = "pending"
                print_job.next_try_at = datetime.now(tz=UTC)
                job_to_enqueue = print_job.job_id

            audit_log = AuditLog(
                actor_type="admin",
                actor_admin_id=admin.admin_id,
                action="admin.payment.match",
                target_table="orders",
                target_id=str(order.order_id),
                before_json=None,
                after_json={
                    "payment_record_id": payment_record.pay_id,
                    "match_status": match_status,
                    "matched_by_admin_id": admin.admin_id,
                },
                ip=ip,
                user_agent=user_agent,
            )
            self._session.add(audit_log)

            await self._session.flush()
            await LoyaltyService(self._session, self._settings).award_on_payment(order)

            broadcast_payload = self._build_broadcast_payload(order)
            PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="matched").inc()

        if broadcast_payload is not None:
            try:
                await merchant_notifier.broadcast(broadcast_payload)
            except Exception:
                self._logger.exception(
                    "admin.payment_match.broadcast_failed",
                    order_id=broadcast_payload["order"]["order_id"],
                )

        if job_to_enqueue is not None:
            try:
                enqueue_print_job(job_to_enqueue)
            except Exception:
                self._logger.exception(
                    "admin.payment_match.print_enqueue_failed",
                    job_id=job_to_enqueue,
                )

        return AdminPaymentMatchResponseSchema(
            status="matched",
            payment_record_id=payment_record.pay_id,
            order_id=order.order_id,
            order_number=order.order_number,
            payment_channel=order.payment_channel or "static_qr",
            payment_status=order.payment_status,
        )

    async def _acquire_payment_record(
        self,
        *,
        payload: AdminPaymentMatchRequestSchema,
        amount: Decimal,
        window_start: datetime,
        window_end: datetime,
    ) -> PaymentRecord:
        stmt = select(PaymentRecord).where(PaymentRecord.txn_id == payload.transaction_id)
        bind = self._session.get_bind()
        if payload.transaction_id:
            if bind is not None and bind.dialect.name != "sqlite":
                stmt = stmt.with_for_update()
            record = await self._session.scalar(stmt)
            if record is None:
                record = PaymentRecord(
                    record_type="payment",
                    channel="static_qr",
                    currency="CNY",
                    amount=amount,
                    txn_id=payload.transaction_id,
                    match_status="unmatched",
                    paid_at=self._ensure_timezone(payload.paid_at),
                    qr_session_id=payload.qr_session_id,
                    raw_notification_json={"trace_id": payload.trace_id} if payload.trace_id else None,
                )
                self._session.add(record)
                await self._session.flush()
            elif record.match_status != "unmatched":
                PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="conflict").inc()
                raise PaymentMatchConflictError("Payment record already matched.")
            else:
                record.amount = amount
                if payload.qr_session_id:
                    record.qr_session_id = payload.qr_session_id
                if bind is not None and bind.dialect.name != "sqlite":
                    await self._session.refresh(record, with_for_update=True)
            return record

        base_stmt = select(PaymentRecord).where(
            PaymentRecord.record_type == "payment",
            PaymentRecord.channel == "static_qr",
            PaymentRecord.match_status == "unmatched",
            PaymentRecord.amount == amount,
            PaymentRecord.paid_at >= window_start,
            PaymentRecord.paid_at <= window_end,
        )
        if payload.qr_session_id:
            base_stmt = base_stmt.where(
                or_(
                    PaymentRecord.qr_session_id == payload.qr_session_id,
                    PaymentRecord.qr_session_id.is_(None),
                )
            )
        if bind is not None and bind.dialect.name != "sqlite":
            base_stmt = base_stmt.with_for_update()

        result = await self._session.execute(base_stmt.order_by(PaymentRecord.paid_at))
        record = result.scalars().first()
        if record:
            if payload.qr_session_id and not record.qr_session_id:
                record.qr_session_id = payload.qr_session_id
            return record

        record = PaymentRecord(
            record_type="payment",
            channel="static_qr",
            currency="CNY",
            amount=amount,
            txn_id=payload.transaction_id,
            match_status="unmatched",
            paid_at=self._ensure_timezone(payload.paid_at),
            qr_session_id=payload.qr_session_id,
            raw_notification_json={"trace_id": payload.trace_id} if payload.trace_id else None,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def _find_candidate_orders(
        self,
        *,
        amount: Decimal,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Order]:
        stmt = (
            select(Order)
            .where(
                Order.payment_status == "pending",
                Order.status == "pending_payment",
                Order.created_at >= window_start,
                Order.created_at <= window_end,
            )
            .order_by(Order.created_at.asc())
        )
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self._session.execute(stmt)
        candidates: list[Order] = []
        for order in result.scalars():
            order_amount = Decimal(str(order.total_price)).quantize(Decimal("0.01"))
            if order_amount == amount:
                candidates.append(order)
        return candidates

    async def _load_order_by_id(self, order_id: int) -> Order:
        bind = self._session.get_bind()
        stmt = select(Order).where(Order.order_id == order_id)
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        order = await self._session.scalar(stmt)
        if order is None:
            PAYMENT_MATCH_ATTEMPT_TOTAL.labels(result="not_found").inc()
            raise PaymentMatchNotFoundError("Order not found.")
        return order

    @staticmethod
    def _ensure_timezone(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _build_candidate_schema(order: Order, paid_at: datetime) -> AdminPaymentMatchCandidateSchema:
        reference_time = order.updated_at or order.created_at or datetime.now(tz=UTC)
        reference_time = PaymentMatchService._ensure_timezone(reference_time)
        paid_at = PaymentMatchService._ensure_timezone(paid_at)
        time_diff = abs(int((paid_at - reference_time).total_seconds()))
        return AdminPaymentMatchCandidateSchema(
            order_id=order.order_id,
            order_number=order.order_number,
            total_price=float(order.total_price),
            time_diff_seconds=time_diff,
            match_score=None,
        )

    async def _ensure_print_job(self, order: Order) -> PrintJob | None:
        stmt = select(PrintJob).where(PrintJob.order_id == order.order_id)
        result = await self._session.execute(stmt)
        job = result.scalar_one_or_none()
        if job is not None:
            return job
        job = PrintJob(order_id=order.order_id, status="pending")
        self._session.add(job)
        await self._session.flush()
        return job

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
