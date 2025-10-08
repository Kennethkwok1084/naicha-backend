from __future__ import annotations

import asyncio
import os

from app.core.settings import get_settings
from app.models.accounts import Admin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def seed_admin() -> None:
    settings = get_settings()
    username = os.environ.get("NAICHA_DEV_ADMIN_USERNAME", "admin")
    password_hash = os.environ.get("NAICHA_DEV_ADMIN_HASH")

    if not password_hash:
        raise SystemExit("Environment variable NAICHA_DEV_ADMIN_HASH is required (bcrypt hash).")

    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(select(Admin).where(Admin.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Admin '{username}' already exists, skipping.")
        else:
            session.add(Admin(username=username, password_hash=password_hash, role="admin"))
            await session.commit()
            print(f"Admin '{username}' created.")

    await engine.dispose()


def main() -> None:
    asyncio.run(seed_admin())


if __name__ == "__main__":
    main()
