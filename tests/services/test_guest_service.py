from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.orders import IdempotencyKey
from app.services.guest import GuestSessionService


@pytest.mark.asyncio
async def test_issue_session_reuses_existing_when_valid(db_session) -> None:
    future = datetime.now(tz=UTC) + timedelta(minutes=10)
    record = IdempotencyKey(
        idempotency_key="gs_existing_valid",
        scope=GuestSessionService.SCOPE,
        expire_at=future,
    )
    db_session.add(record)
    await db_session.flush()

    service = GuestSessionService(db_session)
    session_id, expires_at = await service.issue_session("gs_existing_valid")

    assert session_id == "gs_existing_valid"
    assert expires_at > future


@pytest.mark.asyncio
async def test_issue_session_creates_new_when_expired(db_session) -> None:
    past = datetime.now(tz=UTC) - timedelta(minutes=1)
    expired = IdempotencyKey(
        idempotency_key="gs_expired",
        scope=GuestSessionService.SCOPE,
        expire_at=past,
    )
    db_session.add(expired)
    await db_session.flush()

    service = GuestSessionService(db_session)
    session_id, expires_at = await service.issue_session("gs_expired")

    assert session_id.startswith("gs_")
    assert session_id != "gs_expired"
    assert expires_at > datetime.now(tz=UTC)
