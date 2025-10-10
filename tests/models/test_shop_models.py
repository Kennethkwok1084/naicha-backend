from __future__ import annotations

import pytest
from app.models.shop import ShopProfile, ShopSetting
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_shop_profile_singleton_defaults(db_session) -> None:
    profile = ShopProfile()
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)

    assert profile.id == 1
    assert profile.is_open is True
    assert profile.timezone == "Asia/Shanghai"

    duplicate_profile = ShopProfile(id=2)
    db_session.add(duplicate_profile)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_shop_setting_upsert_behavior(db_session) -> None:
    setting = ShopSetting(key="TEST_KEY", value="value")
    db_session.add(setting)
    await db_session.flush()
    await db_session.refresh(setting)

    assert setting.value == "value"

    setting.value = "updated"
    await db_session.flush()
    await db_session.refresh(setting)

    assert setting.value == "updated"
