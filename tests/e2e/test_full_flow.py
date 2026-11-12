import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

import app.data.database as database_module
import app.data.loader as loader_module
import app.main as main_module
from _helpers import FakeClock, FakeGateway, FakeInventory, build_kit
from app.config import Settings
from app.data.models import Dispatch, Donor, Hospital, Request

AUTH = {"Authorization": "Bearer hospital-token"}
BODY = dict(hospital_id="H01", blood_group="O-", product="red_cells", units=2,
            urgency="critical")


@pytest_asyncio.fixture(loop_scope="function")
async def client(monkeypatch):
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://")
    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(database_module, "init_engine",
                        lambda _s: create_async_engine("sqlite+aiosqlite://",
                                                       poolclass=StaticPool))
    monkeypatch.setattr(loader_module, "load_kit_data",
                        lambda _s, _e: _load_light_kit())
    app = main_module.create_app()
    transport = httpx.ASGITransport(app=app)
    clock = FakeClock(100.0)
    async with app.router.lifespan_context(app):
        app.state.clock = clock
        app.state.gateway = FakeGateway()
        app.state.inventory = FakeInventory()
        await app.state.dispatcher.stop()
        app.state.dispatcher._clock = clock
        async with app.state.sessionmaker() as session:
            session.add(Hospital(hospital_id="H01", name="Demo Hospital", lat=0.0, lon=0.0))
            await session.commit()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app
            yield c


async def _load_light_kit():
    return build_kit()


def key(value="k-e2e"):
    return {"Idempotency-Key": value}


async def seed_donor(app, donor_id, **overrides):
    defaults = dict(blood_group="O-", sex="M", age=30, weight_kg=70.0, lat=0.0, lon=0.0,
                    area_id="A000", quiet_start_hour=0, quiet_end_hour=0,
                    last_donation_at=None, last_donation_type=None,
                    permanently_excluded=0, notified_90d=0, defer_until=None,
                    defer_days=None)
    defaults.update(overrides)
    async with app.state.sessionmaker() as session:
        session.add(Donor(donor_id=donor_id, **defaults))
        await session.commit()


async def get_request(app, rid) -> Request:
    async with app.state.sessionmaker() as session:
        return await session.get(Request, rid)


async def get_dispatches(app, rid) -> list[Dispatch]:
    async with app.state.sessionmaker() as session:
        result = await session.execute(select(Dispatch).where(Dispatch.request_id == rid))
        return list(result.scalars().all())


async def post_callback(client, event_id, rid, donor, event, sim_time):
    return await client.post("/callbacks/donor-progress",
                             json=dict(event_id=event_id, request_id=rid, donor_id=donor,
                                       event=event, sim_time=sim_time))


@pytest.mark.asyncio
async def test_full_flow_create_wave_donate_replay(client):
    await seed_donor(client.app, "D1")
    await seed_donor(client.app, "D2")
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key()})
    assert created.status_code == 201
    rid = created.json()["request_id"]
    assert created.json()["status"] == "open"

    await client.app.state.dispatcher._tick()

    r = await get_request(client.app, rid)
    assert r.status == "mobilizing" and r.wave_count == 1
    waves = [m for m in client.app.state.gateway.messages if m["template"] == "request_wave"]
    by_donor = {m["donor_id"]: m["notification_id"] for m in waves}
    assert set(by_donor) == {"D1", "D2"}

    for i, donor in enumerate(("D1", "D2"), start=1):
        resp = await client.post("/callbacks/donor-response",
                                 json=dict(event_id=f"ev-a{i}", request_id=rid, donor_id=donor,
                                           notification_id=by_donor[donor], response="accepted",
                                           sim_time=101.0))
        assert resp.status_code == 200
        assert (await post_callback(client, f"ev-r{i}", rid, donor, "en_route",
                                    102.0)).status_code == 200

    assert (await post_callback(client, "ev-do1", rid, "D1", "donated", 103.0)).status_code == 200
    duplicate = await post_callback(client, "ev-do1", rid, "D1", "donated", 103.0)
    assert duplicate.status_code == 200
    assert (await post_callback(client, "ev-do2", rid, "D2", "donated", 104.0)).status_code == 200

    state = (await client.get(f"/requests/{rid}", headers=AUTH)).json()
    assert state["status"] == "fulfilled"
    assert state["confirmed"] == 2
    assert state["en_route"] == 2
    assert state["fulfilled"] == 2
    assert state["shortage"] == 0

    replay = await client.post("/requests", json=BODY, headers={**AUTH, **key()})
    assert replay.status_code == 200 and replay.json()["request_id"] == rid


@pytest.mark.asyncio
async def test_stock_delivery_via_dispatcher(client):
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-stock")})
    rid = created.json()["request_id"]
    client.app.state.inventory.items = [dict(center_id="MC1", blood_group="O-",
                                             product="red_cells", units=2,
                                             expires_sim_min=500.0)]
    client.app.state.clock.set(100.0)
    await client.app.state.dispatcher._tick()

    r = await get_request(client.app, rid)
    assert r.stock_inflight == 2
    dispatches = await get_dispatches(client.app, rid)
    assert len(dispatches) == 1 and dispatches[0].outcome == "created"

    client.app.state.clock.set(dispatches[0].delivery_sim_min)
    await client.app.state.dispatcher._tick()

    r = await get_request(client.app, rid)
    assert r.status == "fulfilled"
    assert r.stock_inflight == 0 and r.fulfilled == 2
    state = (await client.get(f"/requests/{rid}", headers=AUTH)).json()
    assert state["fulfilled"] == 2 and state["shortage"] == 0
