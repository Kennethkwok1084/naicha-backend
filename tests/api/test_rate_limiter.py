from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.rate_limiter import init_rate_limiter, limiter


@pytest.mark.asyncio
async def test_rate_limiter_returns_429_when_exceeded() -> None:
    app = FastAPI()
    original_enabled = limiter.enabled
    limiter.enabled = True
    init_rate_limiter(app)

    @app.get("/limited")
    @limiter.limit("1/minute")
    async def limited_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"message": "ok"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.get("/limited")
        assert ok.status_code == 200

        limited = await client.get("/limited")
        assert limited.status_code == 429
        assert limited.headers.get("X-RateLimit-Remaining") == "0"
        assert "Retry-After" in limited.headers

    limiter.enabled = original_enabled
