from __future__ import annotations

import pytest
from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import User, UserAddress
from httpx import ASGITransport, AsyncClient


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), scope=TokenScope.USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_profile_returns_user_info(db_session) -> None:
    user = User(user_id=101, open_id="openid-me-1", nickname="测试用户", loyalty_points=15)
    db_session.add(user)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/profile", headers=_auth_header(user.user_id))
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["loyalty_points"] == 15
    assert payload["user_id"] == user.user_id


@pytest.mark.asyncio
async def test_get_addresses_returns_list(db_session) -> None:
    user = User(user_id=201, open_id="openid-me-2")
    db_session.add(user)
    await db_session.flush()

    address = UserAddress(
        address_id=1,
        user_id=user.user_id,
        contact_name="张三",
        phone="13800000000",
        address_line="上海市徐汇区",
        is_default=True,
    )
    db_session.add(address)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/addresses", headers=_auth_header(user.user_id))
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["contact_name"] == "张三"


@pytest.mark.asyncio
async def test_me_endpoints_require_auth(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/profile")
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 401
