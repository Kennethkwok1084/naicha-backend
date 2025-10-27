from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest_asyncio
from app.db.base import Base
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(_type, compiler, **kwargs) -> str:
    return "JSON"


@compiles(DOUBLE_PRECISION, "sqlite")
def compile_double_precision_sqlite(_type, compiler, **kwargs) -> str:
    return "FLOAT"


def _resolve_test_database_url() -> str:
    """优先读取 TEST_DATABASE_URL;未显式提供时默认降级为 SQLite。"""
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        return test_url

    database_url = os.getenv("DATABASE_URL")
    if not database_url or not database_url.startswith("sqlite"):
        return "sqlite+aiosqlite:///:memory:"
    return database_url


@pytest_asyncio.fixture(scope="function")
async def model_test_engine():
    """为模型测试提供专用 AsyncEngine。
    
    默认使用 SQLite 内存库。
    可通过设置 TEST_DATABASE_URL(或显式提供 SQLite DATABASE_URL)切换目标数据库。
    """
    database_url = _resolve_test_database_url()
    
    if "sqlite" in database_url:
        engine = create_async_engine(
            database_url,
            future=True,
            poolclass=StaticPool,
        )
    else:
        # PostgreSQL 配置:确保 SSL 参数正确传递
        # 若 URL 中没有 sslmode 参数,默认禁用(适配 PostgreSQL ssl=off)
        if "sslmode=" not in database_url:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=disable"
        
        engine = create_async_engine(
            database_url,
            future=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )

    # SQLite 不支持 NULLS FIRST,移除相关索引
    if "sqlite" in database_url:
        for table in Base.metadata.tables.values():
            indexes_to_remove = {
                index
                for index in table.indexes
                if any(
                    isinstance(expr, UnaryExpression)
                    and getattr(expr, "modifier", None) is operators.nulls_first_op
                    for expr in index.expressions
                )
            }
            for index in indexes_to_remove:
                table.indexes.discard(index)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(model_test_engine: AsyncEngine):
    """提供自动回滚的 AsyncSession, 确保测试间隔离。"""
    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    async with session_factory() as session:
        try:
            async with session.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    await session.execute(table.delete())
            yield session
        finally:
            await session.rollback()
