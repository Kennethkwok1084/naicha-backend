from __future__ import annotations

import asyncio

from app.workers import tasks as tasks_module


def test_reservation_activate_due_orders_skips_when_lock_held(monkeypatch) -> None:
    called = False

    def fake_acquire(name: str, interval: int):
        return False, None, False

    def fake_run(*_: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(tasks_module, "_acquire_task_lock", fake_acquire)
    monkeypatch.setattr(tasks_module.asyncio, "run", fake_run)

    tasks_module.reservation_activate_due_orders()

    assert called is False


def test_reservation_activate_due_orders_releases_lock(monkeypatch) -> None:
    class FakeLock:
        def __init__(self):
            self.released = False

        def owned(self) -> bool:
            return True

        def release(self) -> None:
            self.released = True

    fake_lock = FakeLock()

    async def fake_task() -> None:
        await asyncio.sleep(0)

    def fake_acquire(name: str, interval: int):
        return True, fake_lock, False

    monkeypatch.setattr(tasks_module, "_acquire_task_lock", fake_acquire)
    monkeypatch.setattr(tasks_module, "_reservation_activate_due_orders", fake_task)

    tasks_module.reservation_activate_due_orders()

    assert fake_lock.released is True


def test_cancel_stale_pending_orders_skips_when_lock_held(monkeypatch) -> None:
    called = False

    def fake_acquire(name: str, interval: int):
        return False, None, False

    def fake_run(*_: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(tasks_module, "_acquire_task_lock", fake_acquire)
    monkeypatch.setattr(tasks_module.asyncio, "run", fake_run)

    tasks_module.cancel_stale_pending_orders()

    assert called is False
