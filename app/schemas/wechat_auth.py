"""微信认证相关Schema"""
from pydantic import BaseModel, Field


class WeChatLoginRequest(BaseModel):
    """微信登录请求"""
    code: str = Field(..., min_length=1, max_length=256, description="微信登录code")
    nickname: str | None = Field(None, max_length=100, description="用户昵称")
    avatar_url: str | None = Field(None, max_length=500, description="用户头像URL")


class WeChatLoginResponse(BaseModel):
    """微信登录响应"""
    access_token: str = Field(..., description="访问令牌(Bearer)")
    refresh_token: str = Field(..., description="刷新令牌")
    user_id: int = Field(..., description="用户ID")
    is_new_user: bool = Field(..., description="是否新用户")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(default=7200, description="access_token过期时间(秒)")


class BindPhoneRequest(BaseModel):
    """绑定手机号请求"""
    code: str = Field(..., min_length=1, max_length=256, description="微信手机号code")
    guest_session_id: str | None = Field(None, max_length=100, description="游客会话ID(可选)")


class BindPhoneResponse(BaseModel):
    """绑定手机号响应"""
    phone: str = Field(..., description="脱敏后的手机号")
    from_guest_session: bool = Field(..., description="是否来自游客会话")
    message: str = Field(default="手机号绑定成功", description="结果消息")
