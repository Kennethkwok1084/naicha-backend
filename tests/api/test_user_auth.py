"""
DEPRECATED: 这些测试针对旧的legacy认证路由
新的微信认证功能已在 tests/api/test_wechat_auth.py 和 tests/services/test_wechat_auth_service.py 中完整测试
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.api.routes.users import user_login_legacy
from app.core.security import TokenScope, create_access_token, decode_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import User
from app.models.orders import IdempotencyKey
from app.schemas import UserLoginRequestSchema
from app.services.auth import AuthService
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


@pytest.mark.skip(reason="Legacy route deprecated, see test_wechat_auth.py for new tests")
@pytest.mark.asyncio
async def test_user_login_creates_new_user(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/login",
                json={
                    "code": "mock-openid-1",
                    "nickname": "小明",
                    "avatar_url": "https://example.com/avatar.png",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["nickname"] == "小明"
    assert payload["user"]["loyalty_points"] == 0

    token_payload = decode_access_token(payload["access_token"])
    assert token_payload.scope == TokenScope.USER

    created = await db_session.get(User, int(token_payload.sub))
    assert created is not None
    assert created.open_id == "mock-openid-1"


@pytest.mark.skip(reason="Legacy route deprecated, see test_wechat_auth.py for new tests")
@pytest.mark.asyncio
async def test_user_login_updates_existing_user(db_session) -> None:
    existing = User(user_id=10, open_id="existing-openid", nickname="旧昵称")
    db_session.add(existing)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/login",
                json={
                    "code": "existing-openid",
                    "nickname": "新昵称",
                    "avatar_url": "https://example.com/new.png",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["nickname"] == "新昵称"
    assert data["user"]["avatar_url"] == "https://example.com/new.png"
    assert data["user"]["user_id"] == existing.user_id


@pytest.mark.skip(reason="Legacy route deprecated, see test_wechat_auth.py for new tests")
@pytest.mark.asyncio
async def test_user_login_rejects_blank_code(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/login",
                json={"code": "   "},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Invalid authorization code."


@pytest.mark.asyncio
async def test_user_login_handler_direct_success(db_session) -> None:
    service = AuthService(db_session)
    schema = UserLoginRequestSchema(code="openid-direct", nickname="Direct", avatar_url=None)

    result = await user_login_legacy(payload=schema, auth_service=service)
    assert result.user.nickname == "Direct"
    assert result.access_token


@pytest.mark.asyncio
async def test_user_login_handler_direct_invalid_code(db_session) -> None:
    service = AuthService(db_session)
    schema = UserLoginRequestSchema(code=" ")

    with pytest.raises(HTTPException) as exc:
        await user_login_legacy(payload=schema, auth_service=service)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid authorization code."


@pytest.mark.skip(reason="Legacy route deprecated, see test_wechat_auth.py for new tests")
@pytest.mark.asyncio
async def test_bind_phone_for_logged_in_user(db_session) -> None:
    user = User(user_id=21, open_id="bind-openid")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/phone/bind",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "13800001234"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    data = response.json()
    assert data["phone_number"] == "13800001234"
    await db_session.refresh(user)
    assert (user.preferences_json or {}).get("phone_number") == "13800001234"


@pytest.mark.skip(reason="Legacy route deprecated, see test_wechat_auth.py for new tests")
@pytest.mark.asyncio
async def test_bind_phone_for_guest_session(db_session) -> None:
    guest_session = IdempotencyKey(
        idempotency_key="gs-bind",
        scope="guest_session",
        expire_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )
    db_session.add(guest_session)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/users/phone/bind",
                json={"code": "guest-13900001234", "guest_session_id": "gs-bind"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["phone_number"].startswith("1")
    updated_session = await db_session.get(IdempotencyKey, "gs-bind")
    assert updated_session is not None
    assert (updated_session.response_snapshot or {}).get("phone_number") == payload["phone_number"]
