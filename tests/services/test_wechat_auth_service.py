"""测试微信认证服务"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import User, WeChatUsedCode
from app.services.wechat_auth_service import WeChatAuthService
from app.utils.wechat_client import WeChatAPIError


@pytest.fixture
def mock_wechat_client():
    """模拟微信客户端"""
    with patch("app.services.wechat_auth_service.get_wechat_client") as mock:
        client = MagicMock()
        client.jscode2session = AsyncMock()
        client.get_phone_number = AsyncMock()
        client._mask_phone = MagicMock(return_value="138****5678")
        mock.return_value = client
        yield client


@pytest.mark.asyncio
class TestWeChatAuthService:
    """微信认证服务测试"""

    async def test_login_with_code_success_new_user(
        self, db_session: AsyncSession, mock_wechat_client
    ):
        """测试新用户登录成功"""
        # 准备
        mock_wechat_client.jscode2session.return_value = {
            "openid": "test_openid_123",
            "session_key": "test_session_key",
            "unionid": "test_unionid_123",
        }

        service = WeChatAuthService(db_session)

        # 执行
        result = await service.login_with_code(
            code="test_code_123",
            nickname="测试用户",
            avatar_url="https://example.com/avatar.jpg",
        )

        # 验证
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["user_id"] > 0
        assert result["is_new_user"] is True

        # 验证用户已创建
        user = await db_session.get(User, result["user_id"])
        assert user is not None
        assert user.open_id == "test_openid_123"
        assert user.union_id == "test_unionid_123"
        assert user.nickname == "测试用户"

    async def test_login_with_code_success_existing_user(
        self, db_session: AsyncSession, mock_wechat_client
    ):
        """测试已有用户登录成功"""
        # 准备：先创建用户
        user = User(
            open_id="existing_openid",
            nickname="旧昵称",
            avatar_url="https://example.com/old.jpg",
        )
        db_session.add(user)
        await db_session.commit()

        mock_wechat_client.jscode2session.return_value = {
            "openid": "existing_openid",
            "session_key": "test_session_key",
            "unionid": None,
        }

        service = WeChatAuthService(db_session)

        # 执行
        result = await service.login_with_code(
            code="test_code_456",
            nickname="新昵称",
            avatar_url="https://example.com/new.jpg",
        )

        # 验证
        assert result["user_id"] == user.user_id

        # 验证用户信息已更新
        await db_session.refresh(user)
        assert user.nickname == "新昵称"
        assert user.avatar_url == "https://example.com/new.jpg"

    async def test_login_with_code_reused(self, db_session: AsyncSession, mock_wechat_client):
        """测试code重复使用被拒绝"""
        # 准备：mock微信响应
        mock_wechat_client.jscode2session.return_value = {
            "openid": "some_openid",
            "session_key": "some_session_key",
        }

        # 准备：标记code已使用
        from app.core.security import hash_code

        code_hash = hash_code("reused_code")
        used_code = WeChatUsedCode(
            code_hash=code_hash,
            code_type="login",
            used_by_openid="some_openid",
        )
        db_session.add(used_code)
        await db_session.commit()

        service = WeChatAuthService(db_session)

        # 执行并验证
        with pytest.raises(ValueError, match="登录凭证已使用"):
            await service.login_with_code(code="reused_code")

    async def test_login_wechat_api_error(self, db_session: AsyncSession, mock_wechat_client):
        """测试微信API错误处理"""
        # 准备
        mock_wechat_client.jscode2session.side_effect = WeChatAPIError(40029, "code无效")

        service = WeChatAuthService(db_session)

        # 执行并验证
        with pytest.raises(ValueError, match="微信登录失败"):
            await service.login_with_code(code="invalid_code")

    async def test_bind_phone_number_success(self, db_session: AsyncSession, mock_wechat_client):
        """测试绑定手机号成功"""
        # 准备：创建用户
        user = User(open_id="test_openid", nickname="测试用户")
        db_session.add(user)
        await db_session.commit()

        mock_wechat_client.get_phone_number.return_value = {
            "phone_number": "+86 138 1234 5678",
            "pure_phone_number": "13812345678",
            "country_code": "86",
        }

        service = WeChatAuthService(db_session)

        # 执行
        result = await service.bind_phone_number(
            code="phone_code_123",
            user_id=user.user_id,
            guest_session_id="guest_abc",
        )

        # 验证
        assert result["phone"] == "138****5678"
        assert result["from_guest_session"] is True

        # 验证用户手机号已更新
        await db_session.refresh(user)
        assert user.phone == "13812345678"

    async def test_bind_phone_number_code_reused(
        self, db_session: AsyncSession, mock_wechat_client
    ):
        """测试手机号code重复使用被拒绝"""
        # 准备：创建用户并标记code已使用
        user = User(open_id="test_openid", nickname="测试用户")
        db_session.add(user)

        from app.core.security import hash_code

        code_hash = hash_code("phone_reused_code")
        used_code = WeChatUsedCode(
            code_hash=code_hash,
            code_type="phone",
            used_by_openid="test_openid",
        )
        db_session.add(used_code)
        await db_session.commit()

        service = WeChatAuthService(db_session)

        # 执行并验证
        with pytest.raises(ValueError, match="手机号凭证已使用"):
            await service.bind_phone_number(
                code="phone_reused_code",
                user_id=user.user_id,
            )

    async def test_sanitize_nickname_xss_protection(self, db_session: AsyncSession):
        """测试昵称XSS防护"""
        service = WeChatAuthService(db_session)

        # 测试HTML转义
        nickname = service._sanitize_nickname("<script>alert('xss')</script>")
        assert "<script>" not in nickname
        assert "&lt;script&gt;" in nickname

        # 测试长度限制
        long_nickname = "a" * 100
        sanitized = service._sanitize_nickname(long_nickname)
        assert len(sanitized) == 50

    async def test_sanitize_avatar_url_validation(self, db_session: AsyncSession):
        """测试头像URL验证"""
        service = WeChatAuthService(db_session)

        # 测试有效URL
        valid_url = "https://example.com/avatar.jpg"
        assert service._sanitize_avatar_url(valid_url) == valid_url

        # 测试无效URL（不是http/https）
        invalid_url = "javascript:alert('xss')"
        assert service._sanitize_avatar_url(invalid_url) is None

        # 测试长度限制
        long_url = "https://example.com/" + "a" * 600
        sanitized = service._sanitize_avatar_url(long_url)
        assert len(sanitized) == 500
