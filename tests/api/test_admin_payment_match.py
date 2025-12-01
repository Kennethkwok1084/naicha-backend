from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin, User
from app.models.orders import Order, PaymentRecord, PrintJob
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


def _admin_token(admin_id: int) -> str:
    return create_access_token(subject=str(admin_id), scope=TokenScope.ADMIN)


@pytest.mark.asyncio
async def test_admin_payment_match_auto_success(db_session, monkeypatch) -> None:
    admin = Admin(admin_id=501, username="match-admin", password_hash="x", role="admin")
    user = User(user_id=601, open_id="openid-match")
    paid_at = datetime.now(tz=UTC)

    order = Order(
        order_id=701,
        order_number="MATCH-701",
        total_price=Decimal("28.00"),
        status="pending_payment",
        payment_status="pending",
        order_type="pickup",
        user_id=user.user_id,
    )
    payment = PaymentRecord(
        pay_id=801,
        record_type="payment",
        channel="static_qr",
        currency="CNY",
        amount=Decimal("28.00"),
        txn_id="static-txn-801",
        match_status="unmatched",
        paid_at=paid_at,
    )
    db_session.add_all([admin, user, order, payment])
    await db_session.flush()

    enqueued: list[int] = []

    def fake_enqueue(job_id: int) -> None:
        enqueued.append(job_id)

    side_effects: list[tuple[int, str]] = []

    def fake_side_effect(order_id: int, source: str) -> None:
        side_effects.append((order_id, source))

    # Mock distributed_lock to always succeed in tests
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_distributed_lock(*args, **kwargs):
        yield True  # Always acquire lock successfully

    monkeypatch.setattr("app.services.payment_match.distributed_lock", mock_distributed_lock)
    monkeypatch.setattr("app.services.payment_match.enqueue_print_job", fake_enqueue)
    monkeypatch.setattr(
        "app.services.payment_match.enqueue_payment_side_effects",
        fake_side_effect,
    )

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/payments/match",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "match-auto-1",
                },
                json={
                    "qr_session_id": "qr-session-1",
                    "amount": 28.0,
                    "paid_at": paid_at.isoformat(),
                    "transaction_id": "static-txn-801",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["status"] == "matched"
    assert payload["order_id"] == order.order_id
    assert payload["payment_status"] == "paid"

    await db_session.refresh(order)
    await db_session.refresh(payment)

    assert order.payment_status == "paid"
    assert order.status == "paid"
    assert order.payment_channel == "static_qr"
    assert payment.match_status == "auto_matched"
    assert payment.matched_order_id == order.order_id
    assert payment.matched_by_admin_id == admin.admin_id
    assert payment.qr_session_id == "qr-session-1"

    print_jobs = list(
        (
            await db_session.execute(select(PrintJob).where(PrintJob.order_id == order.order_id))
        ).scalars()
    )
    assert len(print_jobs) == 1
    assert enqueued == [print_jobs[0].job_id]
    assert side_effects == [(order.order_id, "payment_match")]


@pytest.mark.asyncio
async def test_admin_payment_match_ambiguous_returns_candidates(db_session, monkeypatch) -> None:
    admin = Admin(admin_id=510, username="match-amb", password_hash="x", role="admin")
    user = User(user_id=610, open_id="openid-amb")
    db_session.add_all([admin, user])
    await db_session.flush()

    paid_at = datetime.now(tz=UTC)
    for idx in range(2):
        db_session.add(
            Order(
                order_id=720 + idx,
                order_number=f"MATCH-72{idx}",
                total_price=Decimal("18.00"),
                status="pending_payment",
                payment_status="pending",
                order_type="pickup",
                user_id=user.user_id,
            )
        )
    payment = PaymentRecord(
        pay_id=820,
        record_type="payment",
        channel="static_qr",
        currency="CNY",
        amount=Decimal("18.00"),
        match_status="unmatched",
        paid_at=paid_at,
    )
    db_session.add(payment)
    await db_session.flush()

    # Mock distributed_lock to always succeed in tests
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_distributed_lock(*args, **kwargs):
        yield True

    monkeypatch.setattr("app.services.payment_match.distributed_lock", mock_distributed_lock)

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/payments/match",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "match-amb-1",
                },
                json={
                    "qr_session_id": "qr-amb",
                    "amount": 18.0,
                    "paid_at": paid_at.isoformat(),
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 409
    payload = response.json()
    error = payload["error"]
    assert error["message"] == "Multiple matching orders found."
    assert error["result"] == "ambiguous"
    assert len(error["candidates"]) == 2

    await db_session.refresh(payment)
    assert payment.match_status == "unmatched"


@pytest.mark.asyncio
async def test_admin_payment_match_manual_force_success(db_session, monkeypatch) -> None:
    admin = Admin(admin_id=520, username="match-force", password_hash="x", role="admin")
    user = User(user_id=620, open_id="openid-force", loyalty_points=0)
    db_session.add_all([admin, user])
    await db_session.flush()

    paid_at = datetime.now(tz=UTC)

    order_a = Order(
        order_id=730,
        order_number="MATCH-730",
        total_price=Decimal("12.00"),
        status="pending_payment",
        payment_status="pending",
        order_type="pickup",
        user_id=user.user_id,
    )
    order_b = Order(
        order_id=731,
        order_number="MATCH-731",
        total_price=Decimal("12.00"),
        status="pending_payment",
        payment_status="pending",
        order_type="pickup",
        user_id=user.user_id,
    )
    payment = PaymentRecord(
        pay_id=830,
        record_type="payment",
        channel="static_qr",
        currency="CNY",
        amount=Decimal("12.00"),
        match_status="unmatched",
        paid_at=paid_at,
    )
    db_session.add_all([order_a, order_b, payment])
    await db_session.flush()

    enqueued: list[int] = []

    def fake_enqueue(job_id: int) -> None:
        enqueued.append(job_id)

    side_effects: list[tuple[int, str]] = []

    def fake_side_effect(order_id: int, source: str) -> None:
        side_effects.append((order_id, source))

    # Mock distributed_lock to always succeed in tests
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_distributed_lock(*args, **kwargs):
        yield True

    monkeypatch.setattr("app.services.payment_match.distributed_lock", mock_distributed_lock)
    monkeypatch.setattr("app.services.payment_match.enqueue_print_job", fake_enqueue)
    monkeypatch.setattr(
        "app.services.payment_match.enqueue_payment_side_effects",
        fake_side_effect,
    )

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/payments/match",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "match-force-1",
                },
                json={
                    "qr_session_id": "qr-force",
                    "amount": 12.0,
                    "paid_at": paid_at.isoformat(),
                    "force_order_id": order_b.order_id,
                    "trace_id": "trace-force",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["order_id"] == order_b.order_id
    assert side_effects == [(order_b.order_id, "payment_match")]
    assert payload["payment_status"] == "paid"

    await db_session.refresh(order_b)
    await db_session.refresh(payment)

    assert payment.match_status == "manual_matched"
    assert payment.matched_order_id == order_b.order_id
    assert payment.matched_by_admin_id == admin.admin_id
    assert payment.qr_session_id == "qr-force"
    assert order_b.status == "paid"

    print_jobs = list(
        (
            await db_session.execute(select(PrintJob).where(PrintJob.order_id == order_b.order_id))
        ).scalars()
    )
    assert len(print_jobs) == 1
    assert enqueued == [print_jobs[0].job_id]
