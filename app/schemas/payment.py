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
