import pytest

from app.services.allocation_service import AllocationService


def item(center_id="MC1", group="O+", product="red_cells", units=5, expires=500.0):
    return dict(center_id=center_id, blood_group=group, product=product, units=units,
                expires_sim_min=expires, expires_at=None)


@pytest.mark.asyncio
async def test_fefo_nearest_expiry_first(services, make_request, inventory, repos, kit):
    make_request()  # R-001: red_cells O+ needed 4
    inventory.items = [item("MC2", expires=500.0), item("MC1", expires=200.0)]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 4, "shortage": 0}
    body = inventory.dispatches[0]
    assert body["center_id"] == "MC1"
    assert body["units"] == 4
    assert body["hospital_id"] == "H01"
    assert body["recipient_blood_group"] == "O+"
    r = await repos.request.get("R-001")
    assert r.stock_inflight == 4
    dispatch = (await repos.dispatch.list_for_request("R-001"))[0]
    expected_delivery = 100.0 + 10.0 + kit.travel_center_to_hospital[("MC1", "H01")]
    assert dispatch.delivery_sim_min == expected_delivery
    assert dispatch.outcome == "created"


@pytest.mark.asyncio
async def test_expired_items_filtered(services, make_request, inventory, repos):
    make_request()
    inventory.items = [item(expires=100.0), item(expires=99.0)]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 0, "shortage": 4}
    assert inventory.dispatches == []
    r = await repos.request.get("R-001")
    assert r.stock_inflight == 0


@pytest.mark.asyncio
async def test_incompatible_group_filtered(services, make_request, inventory):
    make_request()  # recipient O+, red_cells
    inventory.items = [item(group="A+")]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 0, "shortage": 4}


@pytest.mark.asyncio
async def test_other_product_filtered(services, make_request, inventory):
    make_request()
    inventory.items = [item(product="platelets")]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 0, "shortage": 4}


@pytest.mark.asyncio
async def test_never_dispatch_more_than_need(services, make_request, inventory):
    make_request(units=4)
    inventory.items = [item("MC1", units=5, expires=200.0), item("MC2", units=5, expires=300.0)]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result["dispatched_units"] == 4
    assert sum(b["units"] for b in inventory.dispatches) == 4


@pytest.mark.asyncio
async def test_partial_coverage_shortage(services, make_request, inventory):
    make_request(units=4)
    inventory.items = [item(units=2)]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 2, "shortage": 2}


@pytest.mark.asyncio
async def test_failed_dispatch_leaves_local_state(services, make_request, inventory, repos):
    make_request()
    inventory.items = [item(units=4)]
    inventory.mode = "error"
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 0, "shortage": 4}
    r = await repos.request.get("R-001")
    assert r.stock_inflight == 0
    dispatches = await repos.dispatch.list_for_request("R-001")
    assert len(dispatches) == 1 and dispatches[0].outcome == "failed"


@pytest.mark.asyncio
async def test_replay_dispatch_counted_once(services, make_request, inventory, repos):
    make_request()
    inventory.items = [item(units=4)]
    inventory.mode = "replay"
    first = await services.allocation.allocate("R-001", 100.0)
    second = await services.allocation.allocate("R-001", 100.0)
    assert first["dispatched_units"] == 4
    assert second == {"dispatched_units": 0, "shortage": 0}
    assert len(inventory.dispatches) == 1
    r = await repos.request.get("R-001")
    assert r.stock_inflight == 4


@pytest.mark.asyncio
async def test_terminal_request_not_allocated(services, make_request, inventory):
    make_request(status="cancelled")
    result = await services.allocation.allocate("R-001", 100.0)
    assert result == {"dispatched_units": 0, "shortage": 0}
    assert inventory.dispatches == []


@pytest.mark.asyncio
async def test_unknown_request_noop(services, inventory):
    result = await services.allocation.allocate("R-none", 100.0)
    assert result == {"dispatched_units": 0, "shortage": 0}


@pytest.mark.asyncio
async def test_fefo_second_center_used_after_first_exhausted(services, make_request, inventory):
    make_request(units=4)
    inventory.items = [item("MC2", units=5, expires=500.0),
                       item("MC1", units=5, expires=200.0),
                       item("MC3", units=5, expires=300.0)]
    result = await services.allocation.allocate("R-001", 100.0)
    assert result["dispatched_units"] == 4
    assert inventory.dispatches[0]["center_id"] == "MC1"
