from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.accounts import Coupon, User, UserAddress
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_user_defaults_and_addresses_relationship(db_session) -> None:
    user = User(user_id=1, open_id="openid-accounts-1", nickname="模型测试用户")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.loyalty_points == 0
    assert user.preferences_json is None

    address = UserAddress(
        address_id=1,
        user_id=user.user_id,
        contact_name="测试用户",
        phone="13800000000",
        address_line="测试地址",
    )
    db_session.add(address)
    await db_session.flush()
    await db_session.refresh(address)

    assert address.is_default is False
    assert address.user_id == user.user_id

    result = await db_session.execute(
        select(UserAddress).where(UserAddress.user_id == user.user_id)
    )
    addresses = result.scalars().all()
    assert len(addresses) == 1


@pytest.mark.asyncio
async def test_user_open_id_unique_constraint(db_session) -> None:
    user = User(user_id=1, open_id="openid-unique-1")
    db_session.add(user)
    await db_session.flush()

    duplicate = User(user_id=2, open_id="openid-unique-1")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_coupon_defaults_and_status_constraint(db_session) -> None:
    user = User(user_id=10, open_id="openid-coupon-1")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    coupon = Coupon(coupon_id=1, user_id=user.user_id, type="free_any_drink")
    db_session.add(coupon)
    await db_session.flush()
    await db_session.refresh(coupon)

    assert coupon.status == "active"
    assert coupon.issued_at is not None
    assert coupon.issued_at <= datetime.now(UTC).replace(tzinfo=None)

    invalid_coupon = Coupon(
        coupon_id=2, user_id=user.user_id, type="free_any_drink", status="invalid"
    )
    db_session.add(invalid_coupon)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()
