from __future__ import annotations

import pytest

from app.utils import distributed_lock as lock_module


class _DummyConn:
    def __init__(self) -> None:
        self.closed = False

    async def execute(self, *args, **kwargs):
        return None

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_distributed_lock_uses_db_fallback(monkeypatch, db_session) -> None:
    async def fake_acquire_db_lock(**kwargs):
        return True, _DummyConn(), 123

    async def fake_release_db_lock(conn, lock_id):
        conn.closed = True
        fake_release_db_lock.last_lock_id = lock_id

    fake_release_db_lock.last_lock_id = None

    monkeypatch.setattr(lock_module, "_get_redis_client", lambda: None)
    monkeypatch.setattr(lock_module, "_acquire_db_lock", fake_acquire_db_lock)
    monkeypatch.setattr(lock_module, "_release_db_lock", fake_release_db_lock)

    async with lock_module.distributed_lock(
        "payment_match:txn:1",
        timeout=5,
        session=db_session,
    ) as acquired:
        assert acquired is True

    assert fake_release_db_lock.last_lock_id == 123


@pytest.mark.asyncio
async def test_distributed_lock_fallback_failure(monkeypatch, db_session) -> None:
    async def fake_acquire_db_lock(**kwargs):
        return False, None, None

    monkeypatch.setattr(lock_module, "_get_redis_client", lambda: None)
    monkeypatch.setattr(lock_module, "_acquire_db_lock", fake_acquire_db_lock)

    async with lock_module.distributed_lock(
        "payment_match:txn:2",
        timeout=5,
        session=db_session,
    ) as acquired:
        assert acquired is False
