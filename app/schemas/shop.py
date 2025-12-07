from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ShopFeaturesSchema(BaseModel):
    multi_category_enabled: bool
    reservation_enabled: bool
    want_enabled: bool


class ShopLocationSchema(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class ShopProfileSchema(BaseModel):
    name: str
    address: str
    phone: str
    announcement: str | None = None
    logo_url: str | None = None
    updated_at: str | None = None
    # 配送政策
    delivery_notes: list[str] = Field(default_factory=list, description="配送政策说明（多段）")
    supports_pickup: bool = Field(default=True, description="是否支持到店自取")
    supports_delivery: bool = Field(default=True, description="是否支持外卖配送")
    # 配送费用配置
    min_delivery_amount: str | None = Field(default=None, description="最低配送金额")
    delivery_fee: str | None = Field(default=None, description="配送费")
    free_delivery_amount: str | None = Field(default=None, description="免配送费金额")


class ShopStatusSchema(BaseModel):
    is_open: bool
    delivery_radius_m: int
    timezone: str
    open_hours: list[dict[str, Any]] | None = None
    location: ShopLocationSchema | None = None
    features: ShopFeaturesSchema
    # 今日营业时间可读文案
    business_hours_today: str | None = Field(
        default=None, description="今日营业时间文案，如'营业中 09:00-21:00'"
    )


class DeliveryCheckRequestSchema(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class DeliveryCheckResponseSchema(BaseModel):
    deliverable: bool
    distance_m: float
