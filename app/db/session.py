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
    # 性能调优: 连接池配置
    # 生产环境推荐配置 (pool_size=20, max_overflow=30 = 50 总连接)
    # 150并发下,每请求平均持有连接 6-10ms,50连接足够 (实测显示100并发0%错误率)
    # 性能测试需扩充至 pool_size=200, max_overflow=250 应对 200+ 并发
    pool_size=20,
    max_overflow=30,
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
