from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.data.database import create_all, get_session, init_engine
from app.data.models import Base, Request

from conftest import make_dispatch, make_event, make_request, make_task


EXPECTED_TABLES = {
    "requests",
    "dispatches",
    "events",
    "notifications",
    "donors",
    "hospitals",
    "centers",
    "donor_history",
    "tasks",
}


@pytest.mark.asyncio
async def test_all_tables_created(engine):
    tables = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES <= tables


@pytest.mark.asyncio
async def test_request_idempotency_key_unique(engine):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add(make_request(idempotency_key="dup-key"))
        await session.flush()
        session.add(make_request(id="R-000000000002", idempotency_key="dup-key"))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_event_id_primary_key_unique(engine):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add(make_event(event_id="dup-event"))
        await session.flush()
        session.add(make_event(event_id="dup-event"))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_dispatch_id_primary_key_unique(engine):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add(make_dispatch(dispatch_id="dup-dsp"))
        await session.flush()
        session.add(make_dispatch(dispatch_id="dup-dsp"))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_column_defaults(engine):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        request = make_request()
        session.add(request)
        dispatch = make_dispatch()
        session.add(dispatch)
        task = make_task()
        session.add(task)
        await session.flush()
        assert request.confirmed == 0
        assert request.en_route == 0
        assert request.arrived == 0
        assert request.fulfilled == 0
        assert request.stock_inflight == 0
        assert request.wave_count == 0
        assert dispatch.outcome == "created"
        assert task.status == "pending"
        assert task.attempts == 0


@pytest.mark.asyncio
async def test_init_engine_applies_wal_pragmas(tmp_path):
    db_path = tmp_path / "test.db"
    settings = SimpleNamespace(DATABASE_URL=f"sqlite+aiosqlite:///{db_path}")
    engine = init_engine(settings)
    async with engine.connect() as conn:
        journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
        foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
    assert journal_mode == "wal"
    assert busy_timeout == 10000
    assert foreign_keys == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_init_engine_accepts_lowercase_settings(tmp_path):
    db_path = tmp_path / "lower.db"
    settings = SimpleNamespace(database_url=f"sqlite+aiosqlite:///{db_path}")
    engine = init_engine(settings)
    async with engine.connect() as conn:
        journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
    assert journal_mode == "wal"
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_session_commits_on_success(tmp_path):
    db_path = tmp_path / "commit.db"
    settings = SimpleNamespace(DATABASE_URL=f"sqlite+aiosqlite:///{db_path}")
    engine = init_engine(settings)
    await create_all(engine)

    async for session in get_session():
        session.add(make_request(idempotency_key="commit-key"))

    async for session in get_session():
        assert (await session.get(Request, "R-000000000001")) is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_error(tmp_path):
    db_path = tmp_path / "rollback.db"
    settings = SimpleNamespace(DATABASE_URL=f"sqlite+aiosqlite:///{db_path}")
    engine = init_engine(settings)
    await create_all(engine)

    with pytest.raises(IntegrityError):
        async for session in get_session():
            session.add(make_request(idempotency_key="rollback-key"))
            session.add(make_request(id="R-000000000002", idempotency_key="rollback-key"))
            await session.flush()

    async for session in get_session():
        result = await session.execute(text("SELECT COUNT(*) FROM requests"))
        assert result.scalar_one() == 0

    await engine.dispose()
