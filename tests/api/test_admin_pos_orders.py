from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin, User
from app.models.catalog import Category, Product, ProductSpecMapping, SpecGroup, SpecOption
from app.models.orders import AuditLog, Order, PrintJob
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def _seed_menu(db_session) -> None:
    category = Category(category_id=9001, name="POS 菜单", sort_order=1)
    product = Product(
        product_id=9001,
        category_id=category.category_id,
        name="POS 奶茶",
        description="前台热销款",
        base_price=Decimal("18.00"),
        status="active",
        inventory_status="in_stock",
    )
    group = SpecGroup(group_id=9001, name="甜度", sort_order=1)
    option = SpecOption(
        option_id=9001,
        group_id=group.group_id,
        name="标准糖",
        price_modifier=Decimal("0.00"),
        inventory_status="in_stock",
        sort_order=1,
    )
    mapping = ProductSpecMapping(
        mapping_id=9001,
        product_id=product.product_id,
        group_id=group.group_id,
    )
    db_session.add_all([category, product, group, option, mapping])
    await db_session.flush()


def _admin_token(admin_id: int) -> str:
    return create_access_token(subject=str(admin_id), scope=TokenScope.ADMIN)


@pytest.mark.asyncio
async def test_pos_order_cash_success(db_session) -> None:
    await _seed_menu(db_session)
    admin = Admin(admin_id=101, username="pos-admin", password_hash="x", role="admin")
    user = User(user_id=501, open_id="buyer-openid")
    db_session.add_all([admin, user])
    await db_session.flush()

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "pos-idem-1",
                },
                json={
                    "items": [{"product_id": 9001, "quantity": 1, "spec_option_ids": [9001]}],
                    "payment_channel": "cash",
                    "notes": "少冰",
                    "print_job": True,
                    "buyer_open_id": "buyer-openid",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["payment_status"] == "paid"
    assert payload["payment_channel"] == "cash"
    assert payload["print_job_id"] is not None

    order = await db_session.get(Order, payload["order_id"])
    assert order is not None
    assert order.source == "pos"
    assert order.payment_status == "paid"
    assert order.payment_channel == "cash"
    assert order.created_by_admin_id == admin.admin_id
    assert order.status == "paid"

    jobs = await db_session.execute(
        select(PrintJob).where(PrintJob.order_id == order.order_id)
    )
    job_records = list(jobs.scalars())
    assert len(job_records) == 1
    assert job_records[0].job_id == payload["print_job_id"]

    audits = await db_session.execute(
        select(AuditLog).where(AuditLog.target_id == str(order.order_id))
    )
    audit_records = list(audits.scalars())
    assert len(audit_records) == 1
    assert audit_records[0].action == "pos.order.create"


@pytest.mark.asyncio
async def test_pos_order_idempotent_reuse(db_session) -> None:
    await _seed_menu(db_session)
    admin = Admin(admin_id=202, username="idem-admin", password_hash="x", role="admin")
    user = User(user_id=601, open_id="buyer-idem")
    db_session.add_all([admin, user])
    await db_session.flush()

    token = _admin_token(admin.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/api/v1/admin/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "pos-idem-2",
                },
                json={
                    "items": [{"product_id": 9001, "quantity": 1, "spec_option_ids": [9001]}],
                    "payment_channel": "cash",
                    "buyer_open_id": "buyer-idem",
                },
            )
            second = await client.post(
                "/api/v1/admin/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "pos-idem-2",
                },
                json={
                    "items": [{"product_id": 9001, "quantity": 1, "spec_option_ids": [9001]}],
                    "payment_channel": "cash",
                    "buyer_open_id": "buyer-idem",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["order_id"] == second_payload["order_id"]
    assert first_payload["print_job_id"] == second_payload["print_job_id"]

    jobs = await db_session.execute(
        select(PrintJob).where(PrintJob.order_id == first_payload["order_id"])
    )
    job_records = list(jobs.scalars())
    assert len(job_records) == 1


@pytest.mark.asyncio
async def test_pos_order_clerk_restricted_channel(db_session) -> None:
    await _seed_menu(db_session)
    clerk = Admin(admin_id=303, username="clerk", password_hash="x", role="clerk")
    guest = User(user_id=701, open_id="buyer-clerk")
    db_session.add_all([clerk, guest])
    await db_session.flush()

    token = _admin_token(clerk.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Idempotency-Key": "pos-idem-3",
                },
                json={
                    "items": [{"product_id": 9001, "quantity": 1, "spec_option_ids": [9001]}],
                    "payment_channel": "wechat_jsapi",
                    "buyer_open_id": "buyer-clerk",
                },
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 403, response.json()
    payload = response.json()
    assert payload["error"]["message"] == "Clerk role can only use in-store payment channels."
