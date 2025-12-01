from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BIGINT_PK, Base, CreatedAtMixin, TimestampMixin


class WeChatUsedCode(Base, CreatedAtMixin):
    """防止微信code重复使用"""
    __tablename__ = "wechat_used_codes"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    code_type: Mapped[str] = mapped_column(String(20), nullable=False)
    used_by_openid: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint("code_type IN ('login','phone')", name="ck_wechat_used_codes_type"),
        Index("ix_wechat_used_codes_created", "created_at"),
    )


class TokenBlacklist(Base, CreatedAtMixin):
    """token黑名单,用于踢下线"""
    __tablename__ = "token_blacklist"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    token_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_token_blacklist_expires", "expires_at"),
    )


class Admin(Base, CreatedAtMixin):
    __tablename__ = "admins"

    admin_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('admin','manager','clerk')", name="ck_admins_role"),
    )


class User(Base, CreatedAtMixin):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    open_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    union_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    loyalty_points: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    preferences_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    addresses: Mapped[list[UserAddress]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserAddress(Base, TimestampMixin):
    __tablename__ = "user_addresses"

    address_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    lng: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))

    user: Mapped[User] = relationship(back_populates="addresses")


class LoyaltyTransaction(Base, CreatedAtMixin):
    __tablename__ = "loyalty_transactions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.order_id"),
        nullable=True,
    )
    delta_points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "reason IN ('order_paid','refund_rollback','coupon_grant','coupon_use')",
            name="ck_loyalty_transactions_reason",
        ),
    )


class Coupon(Base, CreatedAtMixin):
    __tablename__ = "coupons"

    coupon_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    meta_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_in_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.order_id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("type IN ('free_any_drink')", name="ck_coupons_type"),
        CheckConstraint("status IN ('active','used','expired','void')", name="ck_coupons_status"),
        Index("ix_coupons_user_status", "user_id", "status"),
    )
