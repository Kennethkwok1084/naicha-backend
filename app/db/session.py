from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.settings import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_runtime_url,
    future=True,
    echo=settings.app_env == "dev",
    # 启用详细的SQL执行日志（包含参数）
    echo_pool=settings.app_env == "dev",
    # 性能调优：连接池配置
    # 高并发压测场景下扩充池容量，避免等待导致的超时 / ROLLBACK
    # 200并发 × 2请求(订单+支付) = 需要400连接
    pool_size=200,
    max_overflow=250,
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
