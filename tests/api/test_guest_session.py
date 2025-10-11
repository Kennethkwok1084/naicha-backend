from __future__ import annotations

import pytest

from app.api.routes.guests import create_guest_session, get_guest_session_service
from app.db.session import get_async_session
from app.main import app
from app.models.orders import IdempotencyKey
from app.schemas import GuestSessionCreateRequestSchema
from app.services.guest import GuestSessionService
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_guest_session_creation(db_session) -> None:
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/guests/session", json={})
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    payload = response.json()
    session_id = payload["guest_session_id"]
    assert session_id.startswith("gs_")

    stored = await db_session.get(IdempotencyKey, session_id)
    assert stored is not None
    assert stored.scope == "guest_session"


@pytest.mark.asyncio
async def test_guest_session_reuse_existing(db_session) -> None:
    record = IdempotencyKey(
        idempotency_key="gs_existing",
        scope="guest_session",
    )
    db_session.add(record)
    await db_session.flush()

    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/guests/session",
                json={"session_token": "gs_existing"},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200
    data = response.json()
    assert data["guest_session_id"] == "gs_existing"


@pytest.mark.asyncio
async def test_guest_session_handler_direct(db_session) -> None:
    service = GuestSessionService(db_session)
    payload = GuestSessionCreateRequestSchema(session_token=None)

    response = await create_guest_session(payload=payload, service=service)
    assert response.guest_session_id.startswith("gs_")
