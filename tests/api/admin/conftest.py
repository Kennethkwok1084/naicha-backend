"""Admin API 测试 fixtures"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import Admin
from app.core.security import hash_password


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> Admin:
    """创建测试用管理员（admin角色）"""
    admin = Admin(
        username="test_admin",
        password_hash=hash_password("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession) -> Admin:
    """创建测试用经理（manager角色）"""
    manager = Admin(
        username="test_manager",
        password_hash=hash_password("manager123"),
        role="manager",
    )
    db_session.add(manager)
    await db_session.commit()
    await db_session.refresh(manager)
    return manager


@pytest_asyncio.fixture
async def clerk_user(db_session: AsyncSession) -> Admin:
    """创建测试用店员（clerk角色）"""
    clerk = Admin(
        username="test_clerk",
        password_hash=hash_password("clerk123"),
        role="clerk",
    )
    db_session.add(clerk)
    await db_session.commit()
    await db_session.refresh(clerk)
    return clerk


@pytest_asyncio.fixture
async def admin_token(async_client: AsyncClient, admin_user: Admin) -> str:
    """获取admin角色的JWT token"""
    response = await async_client.post(
        "/api/v1/admin/login",
        json={"username": "test_admin", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]


@pytest_asyncio.fixture
async def manager_token(async_client: AsyncClient, manager_user: Admin) -> str:
    """获取manager角色的JWT token"""
    response = await async_client.post(
        "/api/v1/admin/login",
        json={"username": "test_manager", "password": "manager123"},
    )
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]


@pytest_asyncio.fixture
async def clerk_token(async_client: AsyncClient, clerk_user: Admin) -> str:
    """获取clerk角色的JWT token"""
    response = await async_client.post(
        "/api/v1/admin/login",
        json={"username": "test_clerk", "password": "clerk123"},
    )
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]


@pytest.fixture
async def cleanup_admins(db_session: AsyncSession):
    """清理测试管理员数据"""
    yield
    await db_session.execute(
        delete(Admin).where(Admin.username.in_(["test_admin", "test_manager", "test_clerk"]))
    )
    await db_session.commit()
