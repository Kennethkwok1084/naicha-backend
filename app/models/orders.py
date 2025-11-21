from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BIGINT_PK, Base, CreatedAtMixin, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    guest_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    address_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payment_channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'user'")
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.admin_id"), nullable=True
    )
    is_scheduled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("FALSE"), nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pickup_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reservation_slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservation_slots.slot_id", ondelete="SET NULL"),
        nullable=True,
    )
    coupon_id: Mapped[int | None] = mapped_column(
        ForeignKey("coupons.coupon_id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    __table_args__ = (
        CheckConstraint(
            "total_price >= 0",
            name="ck_orders_total_price_non_negative",
        ),
        CheckConstraint(
            "status IN ('pending_payment','paid','in_production','ready_for_pickup','completed','cancelled','refund_pending','refunded')",
            name="ck_orders_status",
        ),
        CheckConstraint(
            "order_type IN ('pickup','delivery')",
            name="ck_orders_order_type",
        ),
        CheckConstraint(
            "payment_status IN ('pending','paid')",
            name="ck_orders_payment_status",
        ),
        CheckConstraint(
            "source IN ('user','pos','system')",
            name="ck_orders_source",
        ),
    )
    __mapper_args__: ClassVar[dict[str, str]] = {"version_id_col": version}


Index("ix_orders_status_created", Order.status, Order.created_at.desc())
Index("ix_orders_user_created", Order.user_id, Order.created_at.desc())
Index(
    "ix_orders_scheduled",
    Order.is_scheduled,
    Order.scheduled_at,
    postgresql_where=Order.is_scheduled.is_(True),
)
Index("ix_orders_source_created", Order.source, Order.created_at.desc())


class OrderItem(Base):
    __tablename__ = "order_items"

    item_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.product_id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    selected_specs_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),)


class PaymentRecord(Base, CreatedAtMixin):
    __tablename__ = "payment_records"

    pay_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    record_type: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="CNY")
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    txn_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    out_trade_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qr_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.order_id", ondelete="SET NULL"),
        nullable=True,
    )
    match_status: Mapped[str] = mapped_column(
        String(20), server_default="unmatched", nullable=False
    )
    matched_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.admin_id"), nullable=True
    )
    match_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_notification_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payment_records_amount_non_negative"),
        CheckConstraint(
            "record_type IN ('payment','refund')", name="ck_payment_records_record_type"
        ),
        CheckConstraint(
            "channel IN ('wechat_jsapi','wechat_native','static_qr','wechat_refund')",
            name="ck_payment_records_channel",
        ),
        CheckConstraint(
            "match_status IN ('unmatched','auto_matched','manual_matched','failed')",
            name="ck_payment_records_match_status",
        ),
        Index("ix_payment_records_time_amount", "paid_at", "amount"),
        Index("ix_payment_records_type_channel", "record_type", "channel"),
        Index("ix_payment_records_order_match", "matched_order_id"),
        Index(
            "ix_payment_records_match_status_paid",
            "match_status",
            "paid_at",
        ),
        Index(
            "ix_payment_records_qr_session_status",
            "qr_session_id",
            "match_status",
        ),
    )


class IdempotencyKey(Base, CreatedAtMixin):
    __tablename__ = "idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    scope: Mapped[str | None] = mapped_column(String(50), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base, CreatedAtMixin):
    __tablename__ = "audit_logs"

    audit_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.admin_id"), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_table: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    curr_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('admin','user','system')",
            name="ck_audit_logs_actor_type",
        ),
    )


class PrintJob(Base, TimestampMixin):
    __tablename__ = "print_jobs"

    job_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    try_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_try_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    printer_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','done','failed')",
            name="ck_print_jobs_status",
        ),
        UniqueConstraint("order_id", name="uq_print_jobs_order_id"),
    )


class WantEvent(Base, CreatedAtMixin):
    __tablename__ = "want_events"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


Index("ix_want_events_product_time", WantEvent.product_id, WantEvent.created_at.desc())
Index(
    "ix_print_jobs_status_next",
    PrintJob.status,
    PrintJob.next_try_at.asc().nulls_first(),
)
