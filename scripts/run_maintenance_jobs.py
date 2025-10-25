#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from app.core.settings import get_settings
from app.db.session import async_session_factory
from app.services.maintenance import MaintenanceService, run_jobs


async def _acquire_jobs(limit: int) -> list[int]:
    settings = get_settings()
    async with async_session_factory() as session:
        service = MaintenanceService(session, settings)
        async with session.begin():
            job_ids = await service.acquire_jobs(limit=limit)
    return job_ids


async def main(limit: int) -> None:
    settings = get_settings()
    job_ids = await _acquire_jobs(limit)
    if not job_ids:
        print("[maintenance] no pending jobs")
        return
    await run_jobs(job_ids, settings=settings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run due maintenance jobs")
    parser.add_argument("--limit", type=int, default=5, help="Maximum jobs to process")
    args = parser.parse_args()
    asyncio.run(main(limit=max(args.limit, 1)))
