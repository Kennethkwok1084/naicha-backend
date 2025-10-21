from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class WechatPaymentNotifySchema(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=100)
    order_number: str = Field(..., min_length=1, max_length=50)
    transaction_id: str = Field(..., min_length=1, max_length=80)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="CNY", pattern="^[A-Z]{3}$")
    channel: Literal["wechat_jsapi", "wechat_native"]
    status: Literal["SUCCESS", "REFUND"] = Field(default="SUCCESS")
    paid_at: datetime
    raw_notification: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def _only_success(cls, value: str) -> str:
        if value != "SUCCESS":
            raise ValueError("Only SUCCESS notifications are supported.")
        return value


class PaymentNotifyResponseSchema(BaseModel):
    status: str


class AdminPaymentMatchRequestSchema(BaseModel):
    qr_session_id: str = Field(..., min_length=1, max_length=64)
    amount: float = Field(..., gt=0)
    paid_at: datetime
    trace_id: str | None = Field(default=None, max_length=80)
    transaction_id: str | None = Field(default=None, max_length=80)
    force_order_id: int | None = Field(default=None, gt=0)

    @field_validator("qr_session_id", "trace_id", "transaction_id", mode="before")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class AdminPaymentMatchCandidateSchema(BaseModel):
    order_id: int
    order_number: str
    total_price: float
    time_diff_seconds: int
    match_score: float | None = None


class AdminPaymentMatchResponseSchema(BaseModel):
    status: Literal["matched"]
    payment_record_id: int
    order_id: int
    order_number: str
    payment_channel: str
    payment_status: str
