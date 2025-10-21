from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InventoryUpdateRequestSchema(BaseModel):
    inventory_status: Literal["in_stock", "sold_out"] = Field(...)


class InventoryProductResponseSchema(BaseModel):
    product_id: int
    inventory_status: Literal["in_stock", "sold_out"]
    updated_at: datetime


class InventorySpecOptionResponseSchema(BaseModel):
    spec_option_id: int
    inventory_status: Literal["in_stock", "sold_out"]
    updated_at: datetime
