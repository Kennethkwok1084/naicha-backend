"""管理员认证测试"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.accounts import Admin


class TestAdminLogin:
    """管理员登录测试"""

    @pytest.mark.asyncio
    async def test_admin_login_success(self, async_client: AsyncClient, admin_user: Admin):
        """测试成功登录"""
        response = await async_client.post(
            "/api/v1/admin/login",
            json={"username": "test_admin", "password": "admin123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "admin" in data
        assert data["admin"]["username"] == "test_admin"
        assert data["admin"]["role"] == "admin"
        assert "permissions" in data["admin"]
        assert isinstance(data["admin"]["permissions"], list)
        assert len(data["admin"]["permissions"]) > 0

    @pytest.mark.asyncio
    async def test_admin_login_invalid_username(self, async_client: AsyncClient, admin_user: Admin):
        """测试错误用户名"""
        response = await async_client.post(
            "/api/v1/admin/login",
            json={"username": "wrong_user", "password": "admin123"},
        )
        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_login_invalid_password(self, async_client: AsyncClient, admin_user: Admin):
        """测试错误密码"""
        response = await async_client.post(
            "/api/v1/admin/login",
            json={"username": "test_admin", "password": "wrong_password"},
        )
        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_login_missing_fields(self, async_client: AsyncClient):
        """测试缺少必填字段"""
        response = await async_client.post(
            "/api/v1/admin/login",
            json={"username": "test_admin"},
        )
        assert response.status_code == 422


class TestAdminMe:
    """获取当前管理员信息测试"""

    @pytest.mark.asyncio
    async def test_get_current_admin_success(self, async_client: AsyncClient, admin_token: str):
        """测试获取当前管理员信息"""
        response = await async_client.get(
            "/api/v1/admin/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "test_admin"
        assert data["role"] == "admin"
        assert "permissions" in data
        assert isinstance(data["permissions"], list)

    @pytest.mark.asyncio
    async def test_get_current_admin_without_token(self, async_client: AsyncClient):
        """测试未携带token访问"""
        response = await async_client.get("/api/v1/admin/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_admin_invalid_token(self, async_client: AsyncClient):
        """测试无效token"""
        response = await async_client.get(
            "/api/v1/admin/me",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        assert response.status_code == 401


class TestRolePermissions:
    """角色权限测试"""

    @pytest.mark.asyncio
    async def test_admin_role_has_all_permissions(
        self, async_client: AsyncClient, admin_token: str
    ):
        """测试admin角色拥有所有权限"""
        response = await async_client.get(
            "/api/v1/admin/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        permissions = response.json()["permissions"]

        # admin应该拥有所有权限
        required_permissions = [
            "dashboard.view",
            "orders.view",
            "orders.edit",
            "orders.refund",
            "products.view",
            "products.edit",
            "members.view",
            "system.admins.manage",
        ]
        for perm in required_permissions:
            assert perm in permissions

    @pytest.mark.asyncio
    async def test_manager_role_limited_permissions(
        self, async_client: AsyncClient, manager_token: str
    ):
        """测试manager角色有限权限"""
        response = await async_client.get(
            "/api/v1/admin/me",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert response.status_code == 200
        permissions = response.json()["permissions"]

        # manager应该有业务权限
        assert "orders.view" in permissions
        assert "orders.edit" in permissions
        assert "products.view" in permissions

        # manager不应该有系统管理权限
        assert "system.admins.manage" not in permissions

    @pytest.mark.asyncio
    async def test_clerk_role_readonly_permissions(
        self, async_client: AsyncClient, clerk_token: str
    ):
        """测试clerk角色只读权限"""
        response = await async_client.get(
            "/api/v1/admin/me",
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        assert response.status_code == 200
        permissions = response.json()["permissions"]

        # clerk应该有只读权限
        assert "orders.view" in permissions
        assert "products.view" in permissions
        assert "orders.pos.create" in permissions  # 可以POS下单

        # clerk不应该有编辑权限
        assert "orders.edit" not in permissions
        assert "orders.refund" not in permissions
        assert "products.edit" not in permissions
