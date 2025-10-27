"""优惠券列表 API 测试"""

from datetime import UTC, datetime

import pytest
from app.models.accounts import Coupon, User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_get_coupons_returns_all_statuses(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试返回所有状态的优惠券"""
    # 创建不同状态的优惠券
    statuses = ["active", "used", "expired", "void"]
    for status in statuses:
        coupon = Coupon(
            user_id=test_user.user_id,
            type="free_any_drink",
            status=status,
            issued_at=datetime.now(tz=UTC),
        )
        session.add(coupon)
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/coupons",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    
    assert "coupons" in data
    assert "stats" in data
    assert len(data["coupons"]) == 4
    
    # 验证统计数据
    stats = data["stats"]
    assert stats["total_count"] == 4
    assert stats["active_count"] == 1
    assert stats["used_count"] == 1
    assert stats["expired_count"] == 1


@pytest.mark.asyncio
async def test_get_coupons_filter_by_active(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试按 active 状态筛选"""
    # 创建多种状态的优惠券
    for status in ["active", "active", "used", "expired"]:
        coupon = Coupon(
            user_id=test_user.user_id,
            type="free_any_drink",
            status=status,
            issued_at=datetime.now(tz=UTC),
        )
        session.add(coupon)
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/coupons?status=active",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["coupons"]) == 2
    for coupon in data["coupons"]:
        assert coupon["status"] == "active"


@pytest.mark.asyncio
async def test_get_coupons_filter_by_used(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试按 used 状态筛选"""
    # 创建已使用的优惠券
    for i in range(3):
        coupon = Coupon(
            user_id=test_user.user_id,
            type="free_any_drink",
            status="used" if i < 2 else "active",
            issued_at=datetime.now(tz=UTC),
            used_at=datetime.now(tz=UTC) if i < 2 else None,
            used_in_order_id=100 + i if i < 2 else None,
        )
        session.add(coupon)
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/coupons?status=used",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["coupons"]) == 2
    for coupon in data["coupons"]:
        assert coupon["status"] == "used"
        assert coupon["used_at"] is not None
        assert coupon["used_in_order_id"] is not None


@pytest.mark.asyncio
async def test_get_coupons_correct_counts(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试统计数据正确性"""
    # 创建不同状态的优惠券: 3 active, 2 used, 1 expired
    statuses_count = {"active": 3, "used": 2, "expired": 1}
    for status, count in statuses_count.items():
        for _ in range(count):
            coupon = Coupon(
                user_id=test_user.user_id,
                type="free_any_drink",
                status=status,
                issued_at=datetime.now(tz=UTC),
            )
            session.add(coupon)
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/coupons",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    stats = data["stats"]

    assert stats["total_count"] == 6
    assert stats["active_count"] == 3
    assert stats["used_count"] == 2
    assert stats["expired_count"] == 1


@pytest.mark.asyncio
async def test_get_coupons_empty_for_new_user(
    async_client: AsyncClient,
    test_user_token: str,
):
    """测试新用户无优惠券时返回空列表"""
    response = await async_client.get(
        "/api/v1/me/coupons",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    
    assert data["coupons"] == []
    stats = data["stats"]
    assert stats["total_count"] == 0
    assert stats["active_count"] == 0
    assert stats["used_count"] == 0
    assert stats["expired_count"] == 0


@pytest.mark.asyncio
async def test_get_coupons_requires_auth(
    async_client: AsyncClient,
):
    """测试未认证时拒绝访问"""
    response = await async_client.get("/api/v1/me/coupons")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_coupons_only_returns_own_coupons(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试只返回当前用户自己的优惠券"""
    # 创建另一个用户及其优惠券
    other_user = User(
        open_id="other_openid_456",
        nickname="Other User",
        loyalty_points=0,
    )
    session.add(other_user)
    await session.flush()

    # 为另一个用户创建优惠券
    other_coupon = Coupon(
        user_id=other_user.user_id,
        type="free_any_drink",
        status="active",
        issued_at=datetime.now(tz=UTC),
    )
    session.add(other_coupon)

    # 为测试用户创建优惠券
    my_coupon = Coupon(
        user_id=test_user.user_id,
        type="free_any_drink",
        status="active",
        issued_at=datetime.now(tz=UTC),
    )
    session.add(my_coupon)
    await session.commit()

    # 请求时只应返回自己的优惠券
    response = await async_client.get(
        "/api/v1/me/coupons",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["coupons"]) == 1
    assert data["stats"]["total_count"] == 1


@pytest.mark.asyncio
async def test_get_coupons_includes_all_fields(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
):
    """测试返回的优惠券包含所有必需字段"""
    coupon = Coupon(
        user_id=test_user.user_id,
        type="free_any_drink",
        status="active",
        issued_at=datetime.now(tz=UTC),
        meta_json={"description": "积分兑换"},
    )
    session.add(coupon)
    await session.commit()

    response = await async_client.get(
        "/api/v1/me/coupons",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    coupon_data = data["coupons"][0]

    # 验证所有必需字段
    assert "coupon_id" in coupon_data
    assert "user_id" in coupon_data
    assert "type" in coupon_data
    assert "status" in coupon_data
    assert "issued_at" in coupon_data
    assert "meta_json" in coupon_data
    assert "used_at" in coupon_data
    assert "used_in_order_id" in coupon_data
    assert "created_at" in coupon_data

    assert coupon_data["type"] == "free_any_drink"
    assert coupon_data["status"] == "active"
    assert coupon_data["meta_json"] == {"description": "积分兑换"}


@pytest.mark.asyncio
async def test_get_coupons_invalid_status_filter(
    async_client: AsyncClient,
    test_user_token: str,
):
    """测试无效的状态筛选参数"""
    response = await async_client.get(
        "/api/v1/me/coupons?status=invalid_status",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert response.status_code == 422  # Validation error
