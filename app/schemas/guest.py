from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GuestSessionCreateRequestSchema(BaseModel):
    session_token: str | None = Field(default=None, max_length=80)


class GuestSessionResponseSchema(BaseModel):
    guest_session_id: str
    expires_at: datetime
