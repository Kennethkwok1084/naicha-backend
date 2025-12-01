from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.settings import get_settings
from app.models.accounts import User
from app.models.catalog import Category, Product
from app.models.orders import WantEvent
from app.services.want import (
    WantFeatureDisabledError,
    WantRateLimitError,
    WantService,
    WantTargetNotFoundError,
)


async def _seed_product(db_session, *, status: str = "active") -> Product:
    category = Category(category_id=401, name="想要", sort_order=1)
    product = Product(
        product_id=401,
        category_id=category.category_id,
        name="想要测试奶茶",
        description="",
        base_price=Decimal("12.00"),
        status=status,
        inventory_status="sold_out",
        stock_quantity=0,
    )
    db_session.add_all([category, product])
    await db_session.flush()
    return product


@pytest.mark.asyncio
async def test_record_want_success_user(db_session) -> None:
    product = await _seed_product(db_session)
    user = User(user_id=1001, open_id="want-user")
    db_session.add(user)
    await db_session.flush()

    settings = get_settings()
    service = WantService(db_session, settings)

    event = await service.record_want(
        product_id=product.product_id, user=user, ip=None, user_agent="pytest"
    )
    assert isinstance(event, WantEvent)
    assert event.product_id == product.product_id
    assert event.user_id == user.user_id


@pytest.mark.asyncio
async def test_record_want_rate_limit_per_user(db_session) -> None:
    product = await _seed_product(db_session)
    user = User(user_id=2002, open_id="want-limit")
    db_session.add(user)
    await db_session.flush()

    service = WantService(db_session, get_settings())
    now = datetime.now(tz=UTC)

    await service.record_want(
        product_id=product.product_id, user=user, ip=None, user_agent=None, now=now
    )

    with pytest.raises(WantRateLimitError):
        await service.record_want(
            product_id=product.product_id,
            user=user,
            ip=None,
            user_agent=None,
            now=now + timedelta(seconds=10),
        )

    # After one minute succeeds
    later = now + timedelta(minutes=1, seconds=1)
    event = await service.record_want(
        product_id=product.product_id, user=user, ip=None, user_agent=None, now=later
    )
    assert event.product_id == product.product_id


@pytest.mark.asyncio
async def test_record_want_rate_limit_per_ip(db_session) -> None:
    product = await _seed_product(db_session)
    service = WantService(db_session, get_settings())
    now = datetime.now(tz=UTC)

    await service.record_want(
        product_id=product.product_id, user=None, ip="1.1.1.1", user_agent="pytest", now=now
    )

    with pytest.raises(WantRateLimitError):
        await service.record_want(
            product_id=product.product_id,
            user=None,
            ip="1.1.1.1",
            user_agent="pytest",
            now=now + timedelta(seconds=20),
        )


@pytest.mark.asyncio
async def test_record_want_disabled_flag(db_session) -> None:
    product = await _seed_product(db_session)
    settings = get_settings()
    original = settings.want_enabled
    settings.want_enabled = False
    try:
        service = WantService(db_session, settings)
        with pytest.raises(WantFeatureDisabledError):
            await service.record_want(
                product_id=product.product_id, user=None, ip="1.1.1.1", user_agent=None
            )
    finally:
        settings.want_enabled = original


@pytest.mark.asyncio
async def test_record_want_product_not_active(db_session) -> None:
    await _seed_product(db_session, status="inactive")
    service = WantService(db_session, get_settings())

    with pytest.raises(WantTargetNotFoundError):
        await service.record_want(product_id=401, user=None, ip="1.1.1.2", user_agent=None)


@pytest.mark.asyncio
async def test_get_stats_returns_top_and_series(db_session) -> None:
    product = await _seed_product(db_session)
    service = WantService(db_session, get_settings())

    base_time = datetime(2025, 10, 20, 10, 0, tzinfo=UTC)
    for offset in range(3):
        await service.record_want(
            product_id=product.product_id,
            user=None,
            ip=f"10.0.0.{offset}",
            user_agent=None,
            now=base_time + timedelta(days=offset),
        )

    stats = await service.get_stats(
        range_key="7d", limit=5, reference=base_time + timedelta(days=2)
    )
    assert stats["top_products"][0]["product_id"] == product.product_id
    assert stats["top_products"][0]["total"] == 3
    assert len(stats["daily_series"]) >= 3
