"""积分交易记录 API 测试"""

import pytest
from app.models.accounts import LoyaltyTransaction, User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_get_transactions_returns_paginated_list(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试获取分页的积分交易记录"""
    # 创建多条交易记录
    transactions = []
    for i in range(15):
        tx = LoyaltyTransaction(
            user_id=test_user.user_id,
            order_id=None,
            delta_points=10 if i % 2 == 0 else -5,
            reason="order_paid" if i % 2 == 0 else "coupon_use",
        )
        session.add(tx)
        transactions.append(tx)
    await session.commit()

    # 测试默认分页
    response = await async_client.get(
        "/api/v1/me/loyalty/transactions",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "transactions" in data
    assert "total_count" in data
    assert "limit" in data
    assert "offset" in data
    assert data["total_count"] == 15
    assert len(data["transactions"]) == 10  # 默认 limit=10
    assert data["limit"] == 10
    assert data["offset"] == 0

    # 测试自定义分页
    response = await async_client.get(
        "/api/v1/me/loyalty/transactions?limit=5&offset=5",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["transactions"]) == 5
    assert data["limit"] == 5
    assert data["offset"] == 5


@pytest.mark.asyncio
async def test_get_transactions_empty_for_new_user(
    async_client: AsyncClient,
    test_user_token: str,
):
    """测试新用户无交易记录时返回空列表"""
    response = await async_client.get(
        "/api/v1/me/loyalty/transactions",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["transactions"] == []
    assert data["total_count"] == 0


@pytest.mark.asyncio
async def test_get_transactions_ordered_by_date_desc(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试交易记录按创建时间降序排列"""
    import time

    # 创建3条记录, 确保时间戳不同
    for i, reason in enumerate(["order_paid", "coupon_grant", "coupon_use"]):
        tx = LoyaltyTransaction(
            user_id=test_user.user_id,
            order_id=None,
            delta_points=10 + i,
            reason=reason,
        )
        session.add(tx)
        await session.flush()
        if i < 2:
            time.sleep(0.01)  # 确保时间戳有差异
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/loyalty/transactions",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    transactions = data["transactions"]
    assert len(transactions) == 3

    # 验证降序排列 (最新的在前)
    assert transactions[0]["reason"] == "coupon_use"
    assert transactions[1]["reason"] == "coupon_grant"
    assert transactions[2]["reason"] == "order_paid"


@pytest.mark.asyncio
async def test_get_transactions_respects_limit_bounds(
    async_client: AsyncClient,
    test_user_token: str,
):
    """测试 limit 参数边界检查"""
    # limit 超过最大值应返回错误
    response = await async_client.get(
        "/api/v1/me/loyalty/transactions?limit=101",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 422  # Validation error

    # limit 小于1应返回错误
    response = await async_client.get(
        "/api/v1/me/loyalty/transactions?limit=0",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_transactions_requires_auth(
    async_client: AsyncClient,
):
    """测试未认证时拒绝访问"""
    response = await async_client.get("/api/v1/me/loyalty/transactions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_transactions_only_returns_own_data(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试只返回当前用户自己的交易记录"""
    # 创建另一个用户及其交易记录
    other_user = User(
        open_id="other_openid_123",
        nickname="Other User",
        loyalty_points=0,
    )
    session.add(other_user)
    await session.flush()

    # 为另一个用户创建交易记录
    other_tx = LoyaltyTransaction(
        user_id=other_user.user_id,
        order_id=None,
        delta_points=50,
        reason="order_paid",
    )
    session.add(other_tx)

    # 为测试用户创建交易记录
    my_tx = LoyaltyTransaction(
        user_id=test_user.user_id,
        order_id=None,
        delta_points=10,
        reason="order_paid",
    )
    session.add(my_tx)
    await session.commit()

    # 请求时只应返回自己的记录
    response = await async_client.get(
        "/api/v1/me/loyalty/transactions",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["transactions"][0]["delta_points"] == 10


@pytest.mark.asyncio
async def test_get_transactions_includes_all_fields(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试返回的交易记录包含所有必需字段"""
    tx = LoyaltyTransaction(
        user_id=test_user.user_id,
        order_id=1234,
        delta_points=15,
        reason="order_paid",
    )
    session.add(tx)
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/loyalty/transactions",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    tx_data = data["transactions"][0]

    # 验证所有必需字段
    assert "id" in tx_data
    assert "user_id" in tx_data
    assert "order_id" in tx_data
    assert "delta_points" in tx_data
    assert "reason" in tx_data
    assert "created_at" in tx_data

    assert tx_data["delta_points"] == 15
    assert tx_data["reason"] == "order_paid"
    assert tx_data["order_id"] == 1234
