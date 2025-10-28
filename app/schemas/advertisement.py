from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JumpType = Literal["miniapp_page", "h5", "none"]


class CreativeJumpSchema(BaseModel):
    type: JumpType
    payload: dict[str, Any] | None = None


class AdCreativeBaseSchema(BaseModel):
    title: str
    image_url: str
    jump_type: JumpType
    jump_payload: dict[str, Any] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    enabled: bool = True
    priority: int = 100
    platforms: list[str] = Field(default_factory=lambda: ["miniapp"])
    tags: list[str] = Field(default_factory=list)


class AdCreativeResponseSchema(AdCreativeBaseSchema):
    model_config = ConfigDict(from_attributes=True)

    creative_id: int
    created_at: datetime
    updated_at: datetime


class AdCreativeCreateSchema(AdCreativeBaseSchema):
    pass


class AdCreativeUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jump_type: JumpType | None = None
    jump_payload: dict[str, Any] | None = None
    title: str | None = None
    image_url: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    platforms: list[str] | None = None
    tags: list[str] | None = None


class AdSlotSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_id: int
    code: str
    name: str
    description: str | None = None
    spec: dict[str, Any]
    created_at: datetime


class AdSlotCreateSchema(BaseModel):
    code: str
    name: str
    description: str | None = None
    spec: dict[str, Any] = Field(default_factory=dict)


class AdSlotUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    spec: dict[str, Any] | None = None


class AdPlacementSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    placement_id: int
    slot_code: str
    creative_id: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class AdPlacementDetailSchema(AdPlacementSchema):
    model_config = ConfigDict(from_attributes=True)

    creative: AdCreativeResponseSchema


class AdPlacementCreateSchema(BaseModel):
    slot_code: str
    creative_id: int
    sort_order: int | None = Field(default=None, ge=0)


class AdPlacementOrderUpdateSchema(BaseModel):
    slot_code: str
    creative_ids: list[int]


class AdConfigCreativeSchema(BaseModel):
    creative_id: int
    title: str
    image_url: str
    jump_type: JumpType
    jump_payload: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    priority: int
    sort_order: int


class AdConfigResponseSchema(BaseModel):
    version: int
    slots: dict[str, list[AdConfigCreativeSchema]]


class AdTrackRequestSchema(BaseModel):
    slot_code: str = Field(alias="slot")
    creative_id: int
    user_id: int | None = None
    session_id: str | None = None
