from __future__ import annotations

import pytest
from app.core.security import TokenScope, decode_access_token, hash_password
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_admin_login_success(db_session) -> None:
    admin = Admin(
        admin_id=1,
        username="admin",
        password_hash=hash_password("secret123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/login",
                json={"username": "admin", "password": "secret123"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
    token_payload = decode_access_token(payload["access_token"])
    assert token_payload.scope == TokenScope.ADMIN
    assert token_payload.sub == str(admin.admin_id)


@pytest.mark.asyncio
async def test_admin_login_invalid_credentials(db_session) -> None:
    admin = Admin(
        admin_id=2,
        username="wrong",
        password_hash=hash_password("correct-pass"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/login",
                json={"username": "wrong", "password": "incorrect-pass"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["message"] == "Invalid username or password."
