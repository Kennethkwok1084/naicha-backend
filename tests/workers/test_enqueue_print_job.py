from __future__ import annotations

import asyncio

import pytest
from app.workers import enqueue_print_job, process_print_job
from celery.exceptions import CeleryError


@pytest.mark.asyncio
async def test_enqueue_print_job_fallback_on_celery_error(monkeypatch) -> None:
    triggered = asyncio.Event()

    async def fake_execute_print_job(job_id: int) -> None:
        assert job_id == 42
        triggered.set()

    def fake_apply_async(*args, **kwargs):
        raise CeleryError("cannot reach broker")

    monkeypatch.setattr(process_print_job, "apply_async", fake_apply_async)
    monkeypatch.setattr("app.workers.execute_print_job", fake_execute_print_job)

    enqueue_print_job(42)

    await asyncio.wait_for(triggered.wait(), timeout=0.2)
