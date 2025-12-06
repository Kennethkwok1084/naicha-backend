"""测试微信认证API路由"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.accounts import User


@pytest.mark.asyncio
class TestWeChatAuthAPI:
    """微信认证API测试"""

    async def test_login_success(self, async_client: AsyncClient):
        """测试登录成功"""
        with patch("app.api.routes.wechat_auth.WeChatAuthService") as mock_service_class:
            # 模拟服务返回
            mock_service = mock_service_class.return_value
            mock_service.login_with_code = AsyncMock(
                return_value={
                    "access_token": "test_access_token",
                    "refresh_token": "test_refresh_token",
                    "user_id": 12345,
                    "is_new_user": True,
                }
            )
            
            # 发起请求
            response = await async_client.post(
                "/api/v1/users/login",
                json={
                    "code": "test_code_123",
                    "nickname": "测试用户",
                    "avatar_url": "https://example.com/avatar.jpg",
                },
            )
            
            # 验证
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["access_token"] == "test_access_token"
            assert data["refresh_token"] == "test_refresh_token"
            assert data["user_id"] == 12345
            assert data["is_new_user"] is True
            assert data["token_type"] == "bearer"

    async def test_login_missing_code(self, async_client: AsyncClient):
        """测试缺少code参数"""
        response = await async_client.post(
            "/api/v1/users/login",
            json={},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_login_code_reused(self, async_client: AsyncClient):
        """测试code重复使用"""
        with patch("app.api.routes.wechat_auth.WeChatAuthService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.login_with_code = AsyncMock(
                side_effect=ValueError("登录凭证已使用,请重新获取")
            )
            
            response = await async_client.post(
                "/api/v1/users/login",
                json={"code": "reused_code"},
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "登录凭证已使用" in response.json()["detail"]

    async def test_bind_phone_success(
        self, async_client: AsyncClient, test_user: User
    ):
        """测试绑定手机号成功"""
        with patch("app.api.routes.wechat_auth.WeChatAuthService") as mock_service_class:
            # 模拟服务返回
            mock_service = mock_service_class.return_value
            mock_service.bind_phone_number = AsyncMock(
                return_value={
                    "phone": "138****5678",
                    "from_guest_session": False,
                }
            )
            
            # 生成token
            from app.core.security import create_access_token, TokenScope
            token = create_access_token(
                subject=str(test_user.user_id),
                scope=TokenScope.USER,
                openid=test_user.open_id,
            )
            
            # 发起请求
            response = await async_client.post(
                "/api/v1/users/phone/bind",
                json={"code": "phone_code_123"},
                headers={"Authorization": f"Bearer {token}"},
            )
            
            # 验证
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["phone"] == "138****5678"
            assert data["from_guest_session"] is False
            assert data["message"] == "手机号绑定成功"

    async def test_bind_phone_unauthorized(self, async_client: AsyncClient):
        """测试未登录绑定手机号"""
        response = await async_client.post(
            "/api/v1/users/phone/bind",
            json={"code": "phone_code_123"},
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_bind_phone_with_guest_session(
        self, async_client: AsyncClient, test_user: User
    ):
        """测试带游客会话ID绑定手机号"""
        with patch("app.api.routes.wechat_auth.WeChatAuthService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.bind_phone_number = AsyncMock(
                return_value={
                    "phone": "138****5678",
                    "from_guest_session": True,
                }
            )
            
            from app.core.security import create_access_token, TokenScope
            token = create_access_token(
                subject=str(test_user.user_id),
                scope=TokenScope.USER,
                openid=test_user.open_id,
            )
            
            response = await async_client.post(
                "/api/v1/users/phone/bind",
                json={
                    "code": "phone_code_123",
                    "guest_session_id": "guest_abc123",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["from_guest_session"] is True


@pytest.fixture
async def test_user(db_session):
    """创建测试用户"""
    user = User(
        open_id="test_openid_fixture",
        nickname="测试用户",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
