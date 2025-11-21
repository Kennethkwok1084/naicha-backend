from __future__ import annotations

import itertools
import os
import sys
from pathlib import Path

# 必须在导入 app 模块之前设置路径
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
import pytest_asyncio
from app.core.security import TokenScope, create_access_token
from app.db.base import Base
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression


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


# 进程级单例 engine,避免 SQLite in-memory 每次重建
_test_engine: AsyncEngine | None = None


async def _get_or_create_test_engine() -> AsyncEngine:
    """获取或创建进程级共享的测试 engine。"""
    global _test_engine
    if _test_engine is not None:
        return _test_engine

    database_url = _resolve_test_database_url()
    
    if "sqlite" in database_url:
        _test_engine = create_async_engine(
            database_url,
            future=True,
            poolclass=StaticPool,
        )
    else:
        # PostgreSQL 配置:确保 SSL 参数正确传递
        if "sslmode=" not in database_url:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=disable"
        
        _test_engine = create_async_engine(
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

    # 创建所有表结构
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return _test_engine


async def _reset_database(engine: AsyncEngine) -> None:
    """清空所有表并重置 SQLite 序列,保障测试隔离。"""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        bind = session.get_bind()
        if bind and bind.dialect.name == "sqlite":
            seq_exists = await session.execute(
                text("SELECT name FROM sqlite_master WHERE name='sqlite_sequence'")
            )
            if seq_exists.scalar():
                await session.execute(text("DELETE FROM sqlite_sequence"))
        await session.execute(text("PRAGMA foreign_keys = ON"))
        await session.commit()


@pytest_asyncio.fixture(scope="function")
async def model_test_engine():
    """为模型测试提供共享的 AsyncEngine。

    默认使用 SQLite 内存库。
    可通过设置 TEST_DATABASE_URL(或显式提供 SQLite DATABASE_URL)切换目标数据库。
    """
    engine = await _get_or_create_test_engine()
    await _reset_database(engine)
    try:
        yield engine
    finally:
        await _reset_database(engine)
    # 不关闭 engine,由 pytest 进程结束时自动清理


@pytest_asyncio.fixture
async def db_session(model_test_engine: AsyncEngine):
    """提供自动清理的 AsyncSession,测试间通过禁用外键检查后DELETE隔离数据。"""
    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session
        # 测试结束后清空所有表(SQLite需禁用外键检查)
        try:
            await session.rollback()
            await _reset_database(model_test_engine)
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def session(db_session: AsyncSession) -> AsyncSession:
    """API 测试使用的默认 AsyncSession。"""
    return db_session


@pytest_asyncio.fixture
async def async_client(model_test_engine: AsyncEngine):
    """提供共享的 httpx.AsyncClient, 自动覆写 get_async_session。"""

    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    async def _get_session_override():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_async_session] = _get_session_override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    """创建一个默认测试用户。"""
    user_id = next(_USER_SEQ)
    user = User(open_id=f"test-user-{user_id}", nickname="测试用户", loyalty_points=0, user_id=user_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
def test_user_token(test_user: User) -> str:
    return create_access_token(subject=str(test_user.user_id), scope=TokenScope.USER)
_USER_SEQ = itertools.count(1_000)
