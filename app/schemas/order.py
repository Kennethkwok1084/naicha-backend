from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class OrderItemCreateSchema(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=50)
    spec_option_ids: list[int] = Field(default_factory=list, max_length=10)


class OrderDeliveryAddressSchema(BaseModel):
    contact_name: str
    phone: str
    address_line: str
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class OrderCreateRequestSchema(BaseModel):
    items: list[OrderItemCreateSchema] = Field(..., min_length=1, max_length=30)
    order_type: str = Field(..., pattern="^(pickup|delivery)$")
    notes: str | None = Field(default=None, max_length=500)
    guest_session_id: str | None = Field(default=None, max_length=80)
    address: OrderDeliveryAddressSchema | None = None

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OrderItemSchema(BaseModel):
    item_id: int
    product_id: int | None
    product_name: str
    quantity: int
    unit_price: float
    selected_specs: list[dict[str, Any]]


class OrderResponseSchema(BaseModel):
    order_id: int
    order_number: str
    status: str
    order_type: str
    total_price: float
    created_at: datetime
    items: list[OrderItemSchema]


class OrderPaymentJsapiRequestSchema(BaseModel):
    payer_open_id: str = Field(..., min_length=1, max_length=128)
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OrderPaymentNativeRequestSchema(BaseModel):
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OrderPaymentInitiateResponseSchema(BaseModel):
    order_id: int
    channel: str
    payload: dict[str, Any]


class AdminOrderCreateRequestSchema(BaseModel):
    items: list[OrderItemCreateSchema] = Field(..., min_length=1, max_length=50)
    payment_channel: Literal[
        "wechat_jsapi", "wechat_native", "static_qr", "cash", "pos_card"
    ]
    order_type: Literal["pickup"] = Field(default="pickup")
    notes: str | None = Field(default=None, max_length=500)
    print_job: bool = Field(default=True)
    buyer_open_id: str | None = Field(default=None, max_length=255)
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("buyer_open_id", "guest_session_id", mode="before")
    @classmethod
    def _clean_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class AdminOrderResponseSchema(BaseModel):
    order_id: int
    order_number: str
    status: str
    payment_status: str
    payment_channel: str
    total_price: float
    created_at: datetime
    print_job_id: int | None = None
