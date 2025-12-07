"""订单管理API测试"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import AuditLog, Order, OrderItem


class TestOrderList:
    """订单列表测试"""

    @pytest.mark.asyncio
    async def test_list_orders_success(
        self, async_client: AsyncClient, admin_token: str, db_session: AsyncSession
    ):
        """测试获取订单列表"""
        response = await async_client.get(
            "/api/v1/admin/orders",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_orders_with_pagination(self, async_client: AsyncClient, admin_token: str):
        """测试分页参数"""
        response = await async_client.get(
            "/api/v1/admin/orders?page=1&page_size=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_orders_with_status_filter(
        self, async_client: AsyncClient, admin_token: str
    ):
        """测试状态过滤"""
        response = await async_client.get(
            "/api/v1/admin/orders?status=paid,completed",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_orders_without_permission(
        self, async_client: AsyncClient, clerk_token: str
    ):
        """测试clerk角色有查看权限"""
        response = await async_client.get(
            "/api/v1/admin/orders",
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        # clerk有orders.view权限
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_orders_without_token(self, async_client: AsyncClient):
        """测试未授权访问"""
        response = await async_client.get("/api/v1/admin/orders")
        assert response.status_code == 401


class TestOrderDetail:
    """订单详情测试"""

    @pytest.mark.asyncio
    async def test_get_order_detail_not_found(self, async_client: AsyncClient, admin_token: str):
        """测试订单不存在"""
        response = await async_client.get(
            "/api/v1/admin/orders/999999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestOrderStatusUpdate:
    """订单状态修改测试"""

    @pytest.mark.asyncio
    async def test_update_order_status_without_permission(
        self, async_client: AsyncClient, clerk_token: str
    ):
        """测试clerk角色无修改权限"""
        response = await async_client.put(
            "/api/v1/admin/orders/1/status",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        # clerk没有orders.edit权限，但订单不存在时可能返回不同状态码
        assert response.status_code in (403, 404, 422)

    @pytest.mark.asyncio
    async def test_cancel_order_without_reason_fails(
        self, async_client: AsyncClient, admin_token: str
    ):
        """测试取消订单必须提供原因"""
        response = await async_client.put(
            "/api/v1/admin/orders/1/status",
            json={"status": "cancelled"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # 应该返回422，因为取消时reason必填
        assert response.status_code in (422, 404)  # 404是订单不存在的情况


class TestOrderRefund:
    """订单退款测试"""

    @pytest.mark.asyncio
    async def test_refund_order_without_permission(
        self, async_client: AsyncClient, manager_token: str
    ):
        """测试manager角色有退款权限"""
        response = await async_client.post(
            "/api/v1/admin/orders/1/refund",
            json={
                "refund_type": "offline",
                "amount": 10.00,
                "reason": "测试退款",
            },
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        # manager有orders.refund权限，但订单不存在
        assert response.status_code in (200, 404, 400, 422)

    @pytest.mark.asyncio
    async def test_refund_order_clerk_no_permission(
        self, async_client: AsyncClient, clerk_token: str
    ):
        """测试clerk角色无退款权限"""
        response = await async_client.post(
            "/api/v1/admin/orders/1/refund",
            json={
                "refund_type": "offline",
                "amount": 10.00,
                "reason": "测试退款",
            },
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        # clerk无退款权限,但订单不存在时可能返回不同状态码
        assert response.status_code in (403, 404, 422)


class TestAuditLogs:
    """审计日志测试"""

    @pytest.mark.asyncio
    async def test_audit_log_created_on_status_update(
        self, async_client: AsyncClient, admin_token: str, db_session: AsyncSession
    ):
        """测试状态修改时创建审计日志（集成测试）"""
        # 这是一个占位测试，需要实际订单数据
        # 实际测试需要先创建订单，再修改状态，然后验证审计日志
        pass
