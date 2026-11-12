from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import load_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture(loop_scope="function")
async def real_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}")
    monkeypatch.setenv("KIT_PATH", str(ROOT / "participant_kit"))
    monkeypatch.setenv("PORT", "8010")
    load_settings.cache_clear()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app
            yield c
    load_settings.cache_clear()


@pytest.mark.asyncio
async def test_real_lifespan_starts_and_serves_health(real_client):
    response = await real_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_real_lifespan_loads_kit_and_creates_schema(real_client):
    app = real_client.app
    assert app.state.kit_data is not None
    assert app.state.kit_data.rules.get("age_min") == 18
    async with app.state.sessionmaker() as session:
        tables = (await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))).scalars().all()
    assert "requests" in tables and "donors" in tables and "hospitals" in tables
