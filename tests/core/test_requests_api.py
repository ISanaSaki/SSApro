import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

import app.data.database as database_module
import app.data.loader as loader_module
import app.main as main_module
from _helpers import FakeClock, FakeGateway, FakeInventory, build_kit
from app.config import Settings
from app.data.models import Hospital

AUTH = {"Authorization": "Bearer hospital-token"}
COORD = {"Authorization": "Bearer coordinator-token"}
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
    gateway = FakeGateway()
    inventory = FakeInventory()
    async with app.router.lifespan_context(app):
        app.state.clock = clock
        app.state.gateway = gateway
        app.state.inventory = inventory
        await app.state.dispatcher.stop()
        async with app.state.sessionmaker() as session:
            session.add(Hospital(hospital_id="H01", name="Demo Hospital", lat=0.0, lon=0.0))
            await session.commit()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app
            yield c


async def _load_light_kit():
    return build_kit()


def key(value="key-1"):
    return {"Idempotency-Key": value}


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200 and resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_missing_idempotency_key_400(client):
    resp = await client.post("/requests", json=BODY, headers=AUTH)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "missing_idempotency_key"


@pytest.mark.asyncio
async def test_unauthorized_401(client):
    resp = await client.post("/requests", json=BODY, headers=key())
    assert resp.status_code == 401
    resp = await client.get("/requests/R-none", headers=AUTH)
    assert resp.status_code == 200 or resp.status_code == 404
    resp = await client.get("/requests/R-none")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_group_400(client):
    resp = await client.post("/requests", json={**BODY, "blood_group": "Z+"},
                             headers={**AUTH, **key("k-bad-1")})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_units_bounds_400(client):
    for units in (0, 21, -1):
        resp = await client.post("/requests", json={**BODY, "units": units},
                                 headers={**AUTH, **key(f"k-u-{units}")})
        assert resp.status_code == 400, units


@pytest.mark.asyncio
async def test_extra_field_400(client):
    resp = await client.post("/requests", json={**BODY, "surprise": 1},
                             headers={**AUTH, **key("k-extra")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unknown_hospital_400(client):
    resp = await client.post("/requests", json={**BODY, "hospital_id": "H98"},
                             headers={**AUTH, **key("k-h98")})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_hospital"


@pytest.mark.asyncio
async def test_create_replay_reuse(client):
    first = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-crr")})
    assert first.status_code == 201
    rid = first.json()["request_id"]
    assert first.json()["status"] in ("open", "mobilizing")
    replay = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-crr")})
    assert replay.status_code == 200 and replay.json()["request_id"] == rid
    reuse = await client.post("/requests", json={**BODY, "units": 3},
                              headers={**AUTH, **key("k-crr")})
    assert reuse.status_code == 422
    assert reuse.json()["error"]["code"] == "idempotency_key_reuse"


@pytest.mark.asyncio
async def test_get_request_state(client):
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-get")})
    rid = created.json()["request_id"]
    resp = await client.get(f"/requests/{rid}", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    for field in ("status", "needed", "confirmed", "en_route", "arrived", "fulfilled"):
        assert field in data
    assert data["needed"] == 2
    missing = await client.get("/requests/R-none", headers=AUTH)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_amend_flow(client):
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-amend")})
    rid = created.json()["request_id"]
    resp = await client.post(f"/requests/{rid}/amend", json={"urgency": "urgent"}, headers=AUTH)
    assert resp.status_code == 200 and resp.json()["urgency"] == "urgent"
    unknown = await client.post("/requests/R-none/amend", json={"urgency": "urgent"},
                                headers=AUTH)
    assert unknown.status_code == 404
    await client.post(f"/requests/{rid}/cancel", json={}, headers=AUTH)
    blocked = await client.post(f"/requests/{rid}/amend", json={"urgency": "urgent"},
                                headers=AUTH)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "not_amendable"


@pytest.mark.asyncio
async def test_cancel_twice_noop(client):
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-cancel")})
    rid = created.json()["request_id"]
    first = await client.post(f"/requests/{rid}/cancel", json={}, headers=AUTH)
    second = await client.post(f"/requests/{rid}/cancel", json={}, headers=AUTH)
    assert first.status_code == 200 and second.status_code == 200
    state = (await client.get(f"/requests/{rid}", headers=AUTH)).json()
    assert state["status"] == "cancelled"


@pytest.mark.asyncio
async def test_approve_flow(client):
    created = await client.post("/requests", json={**BODY, "units": 15},
                                headers={**AUTH, **key("k-approve")})
    assert created.status_code == 201
    rid = created.json()["request_id"]
    assert created.json()["status"] == "pending_review"
    wrong = await client.post(f"/requests/{rid}/approve", json={}, headers=AUTH)
    assert wrong.status_code == 401
    ok = await client.post(f"/requests/{rid}/approve", json={}, headers=COORD)
    assert ok.status_code == 200 and ok.json()["status"] == "open"
    again = await client.post(f"/requests/{rid}/approve", json={}, headers=COORD)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "not_approvable"


@pytest.mark.asyncio
async def test_callbacks_contract(client):
    created = await client.post("/requests", json=BODY, headers={**AUTH, **key("k-cb")})
    rid = created.json()["request_id"]
    bad = await client.post("/callbacks/donor-progress",
                            json=dict(event_id="ev-bad", request_id=rid, donor_id="D1",
                                      event="flying", sim_time=1.0))
    assert bad.status_code == 400
    event = dict(event_id="ev-1", request_id=rid, donor_id="D1", event="en_route",
                 sim_time=1.0)
    ok = await client.post("/callbacks/donor-progress", json=event)
    assert ok.status_code == 200
    duplicate = await client.post("/callbacks/donor-progress", json=event)
    assert duplicate.status_code == 200
    state = (await client.get(f"/requests/{rid}", headers=AUTH)).json()
    assert state["en_route"] == 1
    unknown = await client.post("/callbacks/donor-progress",
                                json=dict(event_id="ev-2", request_id="R-none", donor_id="D1",
                                          event="donated", sim_time=1.0))
    assert unknown.status_code == 200
