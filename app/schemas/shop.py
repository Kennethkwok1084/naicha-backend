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


class ShopStatusSchema(BaseModel):
    is_open: bool
    delivery_radius_m: int
    timezone: str
    open_hours: list[dict[str, Any]] | None = None
    location: ShopLocationSchema | None = None
    features: ShopFeaturesSchema


class DeliveryCheckRequestSchema(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class DeliveryCheckResponseSchema(BaseModel):
    deliverable: bool
    distance_m: float
