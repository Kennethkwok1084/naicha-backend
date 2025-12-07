from __future__ import annotations

import pytest

from app.core.security import hash_password
from app.models.accounts import Admin, User
from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_authenticate_admin_success(db_session) -> None:
    admin = Admin(
        admin_id=100,
        username="manager",
        password_hash=hash_password("passw0rd"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    service = AuthService(db_session)
    result = await service.authenticate_admin("manager", "passw0rd")

    assert result is not None
    assert result.admin_id == admin.admin_id


@pytest.mark.asyncio
async def test_authenticate_admin_failure(db_session) -> None:
    admin = Admin(
        admin_id=101,
        username="manager",
        password_hash=hash_password("correct-secret"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    service = AuthService(db_session)
    result_wrong_user = await service.authenticate_admin("missing", "correct-secret")
    assert result_wrong_user is None

    result_wrong_password = await service.authenticate_admin("manager", "wrong")
    assert result_wrong_password is None


@pytest.mark.asyncio
async def test_get_admin_and_user_helpers(db_session) -> None:
    admin = Admin(
        admin_id=301,
        username="helper",
        password_hash=hash_password("secret"),
        role="admin",
    )
    user = User(user_id=501, open_id="openid-helper")
    db_session.add_all([admin, user])
    await db_session.flush()

    service = AuthService(db_session)

    fetched_admin = await service.get_admin_by_id(admin.admin_id)
    assert fetched_admin is not None
    assert fetched_admin.username == "helper"

    fetched_user = await service.get_user_by_id(user.user_id)
    assert fetched_user is not None
    assert fetched_user.open_id == "openid-helper"

    fetched_by_openid = await service.get_user_by_open_id("openid-helper")
    assert fetched_by_openid is not None
    assert fetched_by_openid.user_id == user.user_id


@pytest.mark.asyncio
async def test_ensure_user_creates_and_updates(db_session) -> None:
    service = AuthService(db_session)

    created = await service.ensure_user(
        open_id="openid-new",
        nickname="初次昵称",
        avatar_url="https://cdn/avatar.png",
    )
    assert created.user_id is not None
    assert created.nickname == "初次昵称"
    assert created.avatar_url == "https://cdn/avatar.png"

    # sqlite 路径需要人工维护自增, 再次调用验证更新逻辑
    updated = await service.ensure_user(
        open_id="openid-new",
        nickname="新昵称",
        avatar_url="https://cdn/new.png",
    )
    assert updated.user_id == created.user_id
    assert updated.nickname == "新昵称"
    assert updated.avatar_url == "https://cdn/new.png"

    # 再次调用不改变昵称/头像, 走保持分支
    same = await service.ensure_user(
        open_id="openid-new",
        nickname="新昵称",
        avatar_url="https://cdn/new.png",
    )
    assert same.user_id == created.user_id
