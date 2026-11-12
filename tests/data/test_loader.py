import time
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.data.loader import EPOCH, load_kit_data
from app.data.models import Center, Donor, DonorHistory, Hospital

DONOR_COUNT = 17
HISTORY_COUNT = 4


@pytest.mark.asyncio
async def test_load_counts(engine, kit_settings, session_maker):
    kit_data = await load_kit_data(kit_settings, engine)
    async with session_maker() as session:
        donors = (await session.execute(select(Donor))).scalars().all()
        hospitals = (await session.execute(select(Hospital))).scalars().all()
        centers = (await session.execute(select(Center))).scalars().all()
        history = (await session.execute(select(DonorHistory))).scalars().all()
    assert len(donors) == DONOR_COUNT
    assert len(hospitals) == 2
    assert len(centers) == 2
    assert len(history) == HISTORY_COUNT
    assert kit_data.epoch == EPOCH


@pytest.mark.asyncio
async def test_kit_data_contents(engine, kit_settings):
    kit_data = await load_kit_data(kit_settings, engine)
    assert kit_data.compat["red_cells"]["O+"] == ["O+", "O-"]
    assert kit_data.rules["age_min"] == 18
    assert kit_data.travel_area_to_hospital[("A1", "H01")] == 10.5
    assert kit_data.travel_area_to_hospital[("A2", "H02")] == 40.0
    assert kit_data.travel_area_to_center[("A1", "MC1")] == 5.0
    assert kit_data.travel_center_to_hospital[("MC1", "H01")] == 7.5


@pytest.mark.asyncio
async def test_deferral_latest_event_wins(engine, kit_settings, session_maker):
    await load_kit_data(kit_settings, engine)
    async with session_maker() as session:
        active = await session.get(Donor, "D_defer_active")
        past = await session.get(Donor, "D_defer_past")
    assert active.defer_until == "2027-05-02T00:00:00"
    assert active.defer_days == 90
    assert past.defer_until == "2026-11-28T00:00:00"
    assert past.defer_days == 180


@pytest.mark.asyncio
async def test_missing_kit_file_fails_fast(engine, kit_settings, mini_kit):
    (mini_kit / "rules.yaml").unlink()
    with pytest.raises(FileNotFoundError, match="missing kit file"):
        await load_kit_data(kit_settings, engine)


@pytest.mark.asyncio
async def test_missing_kit_dir_fails_fast(engine):
    settings = SimpleNamespace(KIT_PATH="./definitely-missing-kit-dir")
    with pytest.raises(FileNotFoundError, match="kit path does not exist"):
        await load_kit_data(settings, engine)


@pytest.mark.asyncio
async def test_lowercase_kit_path_settings(engine, mini_kit, session_maker):
    settings = SimpleNamespace(kit_path=str(mini_kit))
    await load_kit_data(settings, engine)
    async with session_maker() as session:
        donors = (await session.execute(select(Donor))).scalars().all()
    assert len(donors) == DONOR_COUNT


@pytest.mark.asyncio
async def test_reload_is_idempotent(engine, kit_settings, session_maker):
    await load_kit_data(kit_settings, engine)
    await load_kit_data(kit_settings, engine)
    async with session_maker() as session:
        donors = (await session.execute(select(Donor))).scalars().all()
        history = (await session.execute(select(DonorHistory))).scalars().all()
    assert len(donors) == DONOR_COUNT
    assert len(history) == HISTORY_COUNT


@pytest.mark.asyncio
async def test_load_time_is_fast(engine, kit_settings):
    start = time.perf_counter()
    await load_kit_data(kit_settings, engine)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
