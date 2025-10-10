from __future__ import annotations

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


@pytest_asyncio.fixture(scope="session")
async def model_test_engine() -> AsyncEngine:
    """为模型测试提供专用 AsyncEngine,使用 SQLite 内存库模拟约束。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
    )

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
            yield session
        finally:
            await session.rollback()
