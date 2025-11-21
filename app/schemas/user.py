from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
