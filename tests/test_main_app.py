from __future__ import annotations

import pytest

from app import main as main_module


@pytest.mark.asyncio
async def test_app_lifespan_calls_dispose(monkeypatch) -> None:
    called = False

    async def fake_dispose() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(main_module, "dispose_engine", fake_dispose)

    app = main_module.create_app()

    async with app.router.lifespan_context(app):
        pass

    assert called is True
