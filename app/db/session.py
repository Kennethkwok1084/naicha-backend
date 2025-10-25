from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_runtime_url,
    future=True,
    echo=settings.app_env == "dev",
    # 启用详细的SQL执行日志(包含参数)
    echo_pool=settings.app_env == "dev",
    # 性能调优: 连接池配置 (支持通过环境变量调整以便区分压测/生产场景)
    pool_size=max(settings.database_pool_size, 1),
    max_overflow=max(settings.database_max_overflow, 0),
    pool_pre_ping=True,
    pool_recycle=3600,
)
async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()
