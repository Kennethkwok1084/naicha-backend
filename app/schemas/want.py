from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WantRecordResponseSchema(BaseModel):
    product_id: int
    created_at: datetime
    source: Literal["user", "guest"]


class WantTopProductSchema(BaseModel):
    product_id: int
    product_name: str | None = None
    total: int


class WantDailyPointSchema(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    count: int


class WantStatsResponseSchema(BaseModel):
    range: str
    start: datetime
    end: datetime
    top_products: list[WantTopProductSchema]
    daily_series: list[WantDailyPointSchema]
