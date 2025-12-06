from __future__ import annotations

from pydantic import BaseModel, Field


class AdminLoginRequestSchema(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)


class TokenSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserLoginRequestSchema(BaseModel):
    code: str = Field(..., min_length=1, max_length=255)
    nickname: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=255)


class UserSummarySchema(BaseModel):
    user_id: int
    nickname: str | None
    avatar_url: str | None
    loyalty_points: int


class UserLoginResponseSchema(TokenSchema):
    user: UserSummarySchema


class AdminInfoSchema(BaseModel):
    """管理员信息"""

    id: str
    username: str
    role: str
    permissions: list[str]


class AdminLoginResponseSchema(BaseModel):
    """管理员登录响应"""

    access_token: str
    token_type: str = "bearer"
    admin: AdminInfoSchema
