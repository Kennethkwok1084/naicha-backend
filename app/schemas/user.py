from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserProfileSchema(BaseModel):
    user_id: int
    nickname: str | None
    avatar_url: str | None
    loyalty_points: int


class UserAddressSchema(BaseModel):
    address_id: int
    contact_name: str | None
    phone: str | None
    address_line: str | None
    lat: float | None
    lng: float | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class UserAddressCreateSchema(BaseModel):
    contact_name: str | None = None
    phone: str | None = None
    address_line: str | None = None
    lat: float | None = None
    lng: float | None = None
    is_default: bool = False


class UserAddressUpdateSchema(BaseModel):
    contact_name: str | None = None
    phone: str | None = None
    address_line: str | None = None
    lat: float | None = None
    lng: float | None = None
    is_default: bool | None = None


class PhoneBindRequestSchema(BaseModel):
    code: str = Field(..., min_length=1, description="getPhoneNumber 返回的 code")
    guest_session_id: str | None = Field(default=None, max_length=80)

    @field_validator("code")
    @classmethod
    def _strip_code(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("code 不能为空")
        return cleaned

    @field_validator("guest_session_id")
    @classmethod
    def _strip_guest_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class PhoneBindResponseSchema(BaseModel):
    phone_number: str
    from_guest_session: bool = False
