"""速率限制装饰器和工具"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.settings import get_settings

# 创建限流器实例
limiter = Limiter(key_func=get_remote_address)


def get_openid_from_request(request: Request) -> str:
    """从请求中提取openid用于限流"""
    # 尝试从token中获取openid
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_access_token

            token = auth_header[7:]
            payload = decode_access_token(token)
            if payload.openid:
                return payload.openid
        except Exception:
            pass

    # 降级到IP
    return get_remote_address(request)


def wechat_rate_limit(calls: int, period: str) -> Callable:
    """
    微信API限流装饰器
    例如: @wechat_rate_limit(calls=10, period="minute")
    """
    limit_string = f"{calls}/{period}"

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            settings = get_settings()
            if not settings.rate_limit_enabled:
                return await func(*args, **kwargs)

            # 从kwargs中获取request
            request = kwargs.get("request")
            if not request:
                # 如果没有request参数,尝试从args中找
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request:
                # 检查限流
                key = get_openid_from_request(request)
                # 这里简化处理,生产环境应使用Redis等
                # slowapi会自动处理限流逻辑

            return await func(*args, **kwargs)

        # 应用slowapi的限流
        return limiter.limit(limit_string)(wrapper)

    return decorator
