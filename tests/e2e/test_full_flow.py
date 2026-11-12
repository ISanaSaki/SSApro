import httpx
import pytest
import pytest_asyncio

from _helpers import FakeClock, FakeGateway, FakeInventory
from app.main import create_app

AUTH = {"Authorization": "Bearer hospital-token"}
BODY = dict(hospital_id="H01", blood_group="O-", product="red_cells", units=2,
            urgency="critical")


@pytest_asyncio.fixture(loop_scope="function")
async def client(store, add_hospital):
    add_hospital("H01")
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        app.state.clock = FakeClock(100.0)
        app.state.gateway = FakeGateway()
        app.state.inventory = FakeInventory()
        await app.state.dispatcher.stop()
        app.state.dispatcher._clock = app.state.clock
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app
            yield c


def key(value="k-e2e"):
    return {"Idempotency-Key": value}


async def post_callback(client, event_id, rid, donor, event, sim_time):
    return await client.post("/callbacks/donor-progress",
                             json=dict(event_id=event_id, request_id=rid, donor_id=donor,
                                       event=event, sim_time=sim_time))


@pytest.mark.asyncio
async def test_full_flow_create_wave_donate_replay(client, make_donor, repos):
    make_donor("D1", blood_group="O-")
    make_donor("D2", blood_group="O-")
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key()})
    assert created.status_code == 201
    rid = created.json()["request_id"]
    assert created.json()["status"] == "open"

    await client.app.state.dispatcher._tick()

    r = await repos.request.get(rid)
    assert r.status == "mobilizing" and r.wave_count == 1
    waves = [m for m in client.app.state.gateway.messages if m["template"] == "request_wave"]
    assert {m["donor_id"] for m in waves} == {"D1", "D2"}

    for i, donor in enumerate(("D1", "D2"), start=1):
        resp = await client.post("/callbacks/donor-response",
                                 json=dict(event_id=f"ev-a{i}", request_id=rid, donor_id=donor,
                                           notification_id="nt-1", response="accepted",
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
async def test_stock_delivery_via_dispatcher(client, repos):
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-stock")})
    rid = created.json()["request_id"]
    client.app.state.inventory.items = [dict(center_id="MC1", blood_group="O-",
                                             product="red_cells", units=2,
                                             expires_sim_min=500.0)]
    client.app.state.clock.set(100.0)
    await client.app.state.dispatcher._tick()

    r = await repos.request.get(rid)
    assert r.stock_inflight == 2
    dispatches = await repos.dispatch.list_for_request(rid)
    assert len(dispatches) == 1 and dispatches[0].outcome == "created"

    client.app.state.clock.set(dispatches[0].delivery_sim_min)
    await client.app.state.dispatcher._tick()

    r = await repos.request.get(rid)
    assert r.status == "fulfilled"
    assert r.stock_inflight == 0 and r.fulfilled == 2
    state = (await client.get(f"/requests/{rid}", headers=AUTH)).json()
    assert state["fulfilled"] == 2 and state["shortage"] == 0
