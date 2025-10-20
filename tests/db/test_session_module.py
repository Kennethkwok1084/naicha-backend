from __future__ import annotations

import pytest
from app.db import session as session_module


class DummySessionContext:
    def __init__(self) -> None:
        self.closed = False

    async def __aenter__(self) -> str:
        return "dummy-session"

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True


class DummyEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_get_async_session_uses_factory(monkeypatch) -> None:
    ctx = DummySessionContext()

    def dummy_factory() -> DummySessionContext:
        return ctx

    monkeypatch.setattr(session_module, "async_session_factory", dummy_factory)

    agen = session_module.get_async_session()
    session = await agen.__anext__()
    assert session == "dummy-session"
    await agen.aclose()
    assert ctx.closed is True


@pytest.mark.asyncio
async def test_dispose_engine(monkeypatch) -> None:
    engine = DummyEngine()
    monkeypatch.setattr(session_module, "engine", engine)

    await session_module.dispose_engine()
    assert engine.disposed is True
