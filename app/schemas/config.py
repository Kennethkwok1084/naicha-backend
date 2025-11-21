from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PublicContactSchema(BaseModel):
    phone: str
    business_hours: str | None = None
    wechat_qr: str | None = None


class PublicLegalSchema(BaseModel):
    privacy_url: str | None = None
    terms_url: str | None = None


class PublicUiSchema(BaseModel):
    eta_fallback_text: str | None = None
    order_confirm_tips: str | None = None
    pickup_guide: str | None = None


class PublicAssetsSchema(BaseModel):
    cdn_base_url: str | None = None


class PublicFeaturesSchema(BaseModel):
    disable_delivery: bool = Field(default=False, description="紧急关闭外卖配送")
    disable_coupons: bool = Field(default=False, description="临时关闭优惠券功能")
    disable_stamps: bool = Field(default=False, description="临时关闭集点功能")


class PublicConfigSchema(BaseModel):
    version: str
    ttl_seconds: int = Field(default=600, ge=1, le=86400)
    contact: PublicContactSchema
    legal: PublicLegalSchema
    ui: PublicUiSchema
    assets: PublicAssetsSchema
    features: PublicFeaturesSchema


class FeatureToggleRequestSchema(BaseModel):
    enabled: bool
    reason: str | None = Field(default=None, max_length=200)


class FeatureToggleResponseSchema(BaseModel):
    config_key: str
    value: bool
    updated_at: datetime
    updated_by_admin_id: int | None = None
