"""Dashboard API测试"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


class TestDashboard:
    """Dashboard接口测试"""

    @pytest.mark.asyncio
    async def test_get_dashboard_day_range(self, async_client: AsyncClient, admin_token: str):
        """测试获取日统计"""
        response = await async_client.get(
            "/api/v1/admin/dashboard?range=day",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "trend" in data
        assert "top_products" in data
        assert "payment_channel_split" in data

    @pytest.mark.asyncio
    async def test_get_dashboard_with_compare(self, async_client: AsyncClient, admin_token: str):
        """测试对比模式"""
        response = await async_client.get(
            "/api/v1/admin/dashboard?range=week&compare=true",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "compare_summary" in data

    @pytest.mark.asyncio
    async def test_get_dashboard_custom_date_range(
        self, async_client: AsyncClient, admin_token: str
    ):
        """测试自定义日期区间"""
        today = date.today()
        start = today - timedelta(days=7)
        
        response = await async_client.get(
            f"/api/v1/admin/dashboard?start_date={start}&end_date={today}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["range"] == "custom"
        assert "start_date" in data
        assert "end_date" in data

    @pytest.mark.asyncio
    async def test_get_dashboard_custom_top_n(self, async_client: AsyncClient, admin_token: str):
        """测试自定义Top商品数量"""
        response = await async_client.get(
            "/api/v1/admin/dashboard?range=day&top_n=20",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "top_products" in data
        assert len(data["top_products"]) <= 20

    @pytest.mark.asyncio
    async def test_get_dashboard_invalid_date_range(
        self, async_client: AsyncClient, admin_token: str
    ):
        """测试无效日期区间"""
        today = date.today()
        future = today + timedelta(days=7)
        
        response = await async_client.get(
            f"/api/v1/admin/dashboard?start_date={future}&end_date={today}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_dashboard_without_permission(
        self, async_client: AsyncClient, clerk_token: str
    ):
        """测试clerk角色有Dashboard查看权限"""
        response = await async_client.get(
            "/api/v1/admin/dashboard?range=day",
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        # clerk有dashboard.view权限
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_dashboard_rate_limit(self, async_client: AsyncClient, admin_token: str):
        """测试限流（30次/分钟）"""
        # 这个测试在实际环境中可能需要较长时间
        # 可以mock rate limiter进行测试
        pass
