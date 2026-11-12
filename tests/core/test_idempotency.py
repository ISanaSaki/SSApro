import asyncio

import pytest

from app.config import Settings
from app.services.request_service import CreateError, RequestService

PAYLOAD = dict(hospital_id="H01", blood_group="O+", product="red_cells", units=2,
               urgency="critical", note=None)


@pytest.mark.asyncio
async def test_create_then_replay_same_key(services, add_hospital, store):
    add_hospital("H01")
    first = await services.request.create_request(PAYLOAD, "k-1", 100.0)
    assert first.created and not first.replay
    assert first.status == "open" and first.needed == 2
    replay = await services.request.create_request(PAYLOAD, "k-1", 105.0)
    assert replay.replay and not replay.created
    assert replay.request_id == first.request_id
    assert len(store.requests) == 1


@pytest.mark.asyncio
async def test_same_key_different_body_rejected(services, add_hospital):
    add_hospital("H01")
    await services.request.create_request(PAYLOAD, "k-2", 100.0)
    result = await services.request.create_request({**PAYLOAD, "units": 3}, "k-2", 100.0)
    assert isinstance(result, CreateError)
    assert result.code == "idempotency_key_reuse" and result.http_status == 422


@pytest.mark.asyncio
async def test_unknown_hospital_no_request_no_task(services, store):
    result = await services.request.create_request(PAYLOAD, "k-3", 100.0)
    assert isinstance(result, CreateError)
    assert result.code == "unknown_hospital" and result.http_status == 400
    assert not store.requests and not store.tasks


@pytest.mark.asyncio
async def test_20_concurrent_same_key_creates_once(services, add_hospital):
    add_hospital("H01")
    results = await asyncio.gather(
        *[services.request.create_request(PAYLOAD, "conc-key", 100.0) for _ in range(20)])
    created = [r for r in results if r.created]
    replays = [r for r in results if r.replay]
    assert len(created) == 1
    assert len(replays) == 19
    assert all(r.request_id == created[0].request_id for r in replays)


@pytest.mark.asyncio
async def test_suspicious_units_hold_pending(services, add_hospital, store):
    add_hospital("H01")
    result = await services.request.create_request({**PAYLOAD, "units": 15}, "k-4", 100.0)
    assert result.status == "pending_review"
    assert not store.tasks


@pytest.mark.asyncio
async def test_burst_hold_second_request(store, kit, clock, repos, add_hospital):
    add_hospital("H01")
    burst_settings = Settings(_env_file=None, burst_max_units=7)
    service = RequestService(repos.request, repos.event, repos.dispatch, repos.task,
                             repos.hospital, kit.rules, burst_settings)
    first = await service.create_request({**PAYLOAD, "units": 8}, "b-1", 100.0)
    assert first.status == "open"
    second = await service.create_request({**PAYLOAD, "units": 8}, "b-2", 100.0)
    assert second.status == "pending_review"


@pytest.mark.asyncio
async def test_open_request_schedules_wave_task(services, add_hospital, store):
    add_hospital("H01")
    await services.request.create_request(PAYLOAD, "k-5", 100.0)
    tasks = [t for t in store.tasks.values()
             if t.task_type == "send_wave" and t.request_id]
    assert len(tasks) == 1
