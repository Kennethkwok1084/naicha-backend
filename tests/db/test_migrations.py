from __future__ import annotations

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.util import CommandError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import get_settings

TEST_DB_NAME = "naicha_test"


@pytest.mark.asyncio
async def test_alembic_upgrade_and_downgrade_cycle() -> None:
    settings = get_settings()
    base_async_url = make_url(settings.database_url)
    base_sync_url = make_url(settings.alembic_sync_url)

    test_async_url = base_async_url.set(database=TEST_DB_NAME)
    test_sync_url = base_sync_url.set(database=TEST_DB_NAME, drivername="postgresql")

    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = str(test_async_url)
    get_settings.cache_clear()

    config = Config("alembic.ini")

    try:
        with psycopg.connect(str(test_sync_url)) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(
            "Skipping migration test: unable to connect with database URL "
            f"'{test_sync_url}'. Error: {exc}"
        )

    engine = create_async_engine(str(test_async_url))
    try:
        try:
            command.downgrade(config, "base")
        except CommandError:
            command.stamp(config, "base")

        command.upgrade(config, "head")

        async with engine.connect() as conn:
            shop_profile_count = await conn.scalar(text("SELECT COUNT(*) FROM shop_profile"))
            assert shop_profile_count == 1

            setting_value = await conn.scalar(
                text("SELECT value FROM shop_settings WHERE key = 'MULTI_CATEGORY_ENABLED'")
            )
            assert setting_value == "false"
    finally:
        try:
            command.downgrade(config, "base")
        except CommandError:
            pass

        await engine.dispose()

        if original_database_url is not None:
            os.environ["DATABASE_URL"] = original_database_url
        else:
            os.environ.pop("DATABASE_URL", None)
        get_settings.cache_clear()
