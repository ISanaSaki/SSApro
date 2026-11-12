import pytest
from types import SimpleNamespace

from app.tasks.dispatcher import BackgroundDispatcher
from tests.core._helpers import Dispatch


class _NullSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def dispatcher_services(repos, services):
    return SimpleNamespace(
        request_repo=repos.request,
        event_repo=repos.event,
        dispatch_repo=repos.dispatch,
        task_repo=repos.task,
        invitation_service=services.invitation,
        sla_service=services.sla,
    )


@pytest.fixture
def dispatcher(settings, clock, dispatcher_services):
    def build_services(session):
        return dispatcher_services

    return BackgroundDispatcher(
        settings=settings,
        clock=clock,
        sessionmaker=lambda: _NullSession(),
        build_services=build_services,
    )


def due_dispatch(store, dispatch_id="DP-1", request_id="R-001", units=2,
                 delivery_sim_min=130.0):
    store.dispatches[dispatch_id] = Dispatch(
        dispatch_id=dispatch_id, request_id=request_id, center_id="MC1",
        blood_group="O+", product="red_cells", units=units, hospital_id="H01",
        recipient_blood_group="O+", created_sim_min=100.0,
        delivery_sim_min=delivery_sim_min, outcome="created")


@pytest.mark.asyncio
async def test_deliver_stock_marks_dispatch_delivered(dispatcher, dispatcher_services, store,
                                                      make_request):
    r = make_request(units=2, needed=2, status="open")
    r.stock_inflight = 2
    due_dispatch(store)

    await dispatcher._deliver_stock(dispatcher_services, 140.0)

    assert store.dispatches["DP-1"].outcome == "delivered"
    assert r.fulfilled == 2
    assert r.stock_inflight == 0
    assert r.status == "fulfilled"
    assert any(e.event_id == "sd-DP-1" and e.kind == "stock_delivery"
               for e in store.events)


@pytest.mark.asyncio
async def test_deliver_stock_partial_keeps_request_active(dispatcher, dispatcher_services, store,
                                                          make_request):
    r = make_request(units=4, needed=4, status="mobilizing")
    r.stock_inflight = 2
    due_dispatch(store)

    await dispatcher._deliver_stock(dispatcher_services, 140.0)

    assert store.dispatches["DP-1"].outcome == "delivered"
    assert r.fulfilled == 2
    assert r.stock_inflight == 0
    assert r.status == "partially_fulfilled"


@pytest.mark.asyncio
async def test_deliver_stock_does_not_double_fulfill(dispatcher, dispatcher_services, store,
                                                     make_request):
    r = make_request(units=2, needed=2, status="open")
    r.stock_inflight = 2
    due_dispatch(store)

    await dispatcher._deliver_stock(dispatcher_services, 140.0)
    store.dispatches["DP-1"].outcome = "created"  # simulate stale state
    await dispatcher._deliver_stock(dispatcher_services, 150.0)

    assert r.fulfilled == 2
    assert len([e for e in store.events if e.event_id == "sd-DP-1"]) == 1


@pytest.mark.asyncio
async def test_deliver_stock_ignores_future_deliveries(dispatcher, dispatcher_services, store,
                                                       make_request):
    r = make_request(units=2, needed=2, status="open")
    r.stock_inflight = 2
    due_dispatch(store, delivery_sim_min=200.0)

    await dispatcher._deliver_stock(dispatcher_services, 140.0)

    assert store.dispatches["DP-1"].outcome == "created"
    assert r.fulfilled == 0
    assert store.events == []
