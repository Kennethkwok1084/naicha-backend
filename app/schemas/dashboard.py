from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DashboardSummarySchema(BaseModel):
    gross_sales: float = Field(default=0)
    order_count: int = Field(default=0)
    avg_ticket: float = Field(default=0)
    refund_amount: float = Field(default=0)


class DashboardTrendPointSchema(BaseModel):
    ts: datetime
    gross_sales: float
    order_count: int


class DashboardTopProductSchema(BaseModel):
    product_id: int | None
    name: str | None
    quantity: int
    gross_sales: float


class DashboardPaymentChannelSchema(BaseModel):
    channel: str
    order_count: int
    gross_sales: float


class DashboardResponseSchema(BaseModel):
    range: Literal["day", "week", "month", "custom"]
    summary: DashboardSummarySchema
    trend: list[DashboardTrendPointSchema]
    top_products: list[DashboardTopProductSchema]
    payment_channel_split: list[DashboardPaymentChannelSchema]
    compare_summary: DashboardSummarySchema | None = None
    start_date: str | None = None  # 自定义日期时返回
    end_date: str | None = None  # 自定义日期时返回
