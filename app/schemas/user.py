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
