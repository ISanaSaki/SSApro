import pytest

from app.data.models import Notification


def response_payload(event_id, request_id, donor_id, response, reason=None, sim_time=1.0):
    return dict(event_id=event_id, request_id=request_id, donor_id=donor_id,
                notification_id="nt-x", response=response, reason=reason, sim_time=sim_time)


def progress_payload(event_id, request_id, donor_id, event, sim_time=1.0):
    return dict(event_id=event_id, request_id=request_id, donor_id=donor_id,
                notification_id="nt-x", event=event, sim_time=sim_time)


def wave_notification(request_id, donor_id):
    return Notification(notification_id="nt-w-" + donor_id, request_id=request_id,
                        donor_id=donor_id, template="request_wave", created_sim_min=100.0,
                        sent_sim_min=100.0, gateway_status=None, response=None)


@pytest.mark.asyncio
async def test_duplicate_event_ignored(services, make_request, repos):
    make_request()
    payload = progress_payload("ev-1", "R-001", "D1", "en_route")
    assert await services.callback.process_donor_progress(payload, 100.0) is True
    assert await services.callback.process_donor_progress(payload, 100.0) is False
    r = await repos.request.get("R-001")
    assert r.en_route == 1


@pytest.mark.asyncio
async def test_unknown_request_accepted_without_counters(services, repos):
    payload = progress_payload("ev-2", "R-none", "D1", "donated")
    assert await services.callback.process_donor_progress(payload, 100.0) is True
    events = await repos.event.list_for_request("R-none")
    assert len(events) == 1 and events[0].event_id == "ev-2"


@pytest.mark.asyncio
async def test_accepted_counted_once_per_donor(services, make_request, repos, gateway):
    make_request()
    assert await services.callback.process_donor_response(
        response_payload("ev-a1", "R-001", "D1", "accepted"), 100.0) is True
    assert await services.callback.process_donor_response(
        response_payload("ev-a2", "R-001", "D1", "accepted"), 100.0) is True
    r = await repos.request.get("R-001")
    assert r.confirmed == 1
    confirmed_msgs = [m for m in gateway.messages if m["template"] == "confirmed"]
    assert len(confirmed_msgs) == 1 and confirmed_msgs[0]["donor_id"] == "D1"


@pytest.mark.asyncio
async def test_declined_no_counter(services, make_request, repos, gateway):
    make_request()
    assert await services.callback.process_donor_response(
        response_payload("ev-d1", "R-001", "D1", "declined", reason="busy"), 100.0) is True
    r = await repos.request.get("R-001")
    assert r.confirmed == 0
    assert gateway.messages == []


@pytest.mark.asyncio
async def test_progress_counters_once_per_donor(services, make_request, repos):
    make_request()
    await services.callback.process_donor_progress(
        progress_payload("ev-r1", "R-001", "D1", "en_route"), 100.0)
    await services.callback.process_donor_progress(
        progress_payload("ev-r2", "R-001", "D1", "en_route"), 100.0)
    await services.callback.process_donor_progress(
        progress_payload("ev-v1", "R-001", "D1", "arrived"), 100.0)
    await services.callback.process_donor_progress(
        progress_payload("ev-v2", "R-001", "D1", "arrived"), 100.0)
    r = await repos.request.get("R-001")
    assert r.en_route == 1 and r.arrived == 1


@pytest.mark.asyncio
async def test_donated_before_arrived_order_independent(services, make_request, repos):
    make_request()
    await services.callback.process_donor_progress(
        progress_payload("ev-do", "R-001", "D1", "donated"), 100.0)
    await services.callback.process_donor_progress(
        progress_payload("ev-ar", "R-001", "D1", "arrived"), 100.0)
    r = await repos.request.get("R-001")
    assert r.fulfilled == 1 and r.arrived == 1


@pytest.mark.asyncio
async def test_screen_events_no_counters(services, make_request, repos):
    make_request()
    for i, event in enumerate(("screen_pass", "screen_fail", "no_show")):
        await services.callback.process_donor_progress(
            progress_payload(f"ev-s{i}", "R-001", "D1", event), 100.0)
    r = await repos.request.get("R-001")
    assert r.confirmed == r.en_route == r.arrived == r.fulfilled == 0


@pytest.mark.asyncio
async def test_donated_fulfills_and_stops_outreach(services, make_request, repos, store, gateway):
    make_request(units=1)
    store.notifications.append(wave_notification("R-001", "D1"))
    store.notifications.append(wave_notification("R-001", "D2"))
    await services.callback.process_donor_response(
        response_payload("ev-a1", "R-001", "D1", "accepted"), 100.0)
    await services.callback.process_donor_response(
        response_payload("ev-a2", "R-001", "D2", "accepted"), 100.0)
    await services.callback.process_donor_progress(
        progress_payload("ev-do", "R-001", "D1", "donated"), 100.0)
    r = await repos.request.get("R-001")
    assert r.status == "fulfilled" and r.fulfilled == 1
    not_needed = [m for m in gateway.messages if m["template"] == "not_needed"]
    assert len(not_needed) == 1 and not_needed[0]["donor_id"] == "D2"


@pytest.mark.asyncio
async def test_gateway_status_no_counters(services, make_request, repos):
    make_request()
    payload = dict(event_id="ev-g", notification_id="nt-1", request_id="R-001",
                   donor_id="D1", status="delivered", sim_time=1.0)
    assert await services.callback.process_gateway_status(payload, 100.0) is True
    r = await repos.request.get("R-001")
    assert r.confirmed == r.en_route == r.arrived == r.fulfilled == 0


@pytest.mark.asyncio
async def test_honest_counting_on_terminal(services, make_request, repos):
    make_request(status="cancelled")
    await services.callback.process_donor_progress(
        progress_payload("ev-do", "R-001", "D1", "donated"), 100.0)
    r = await repos.request.get("R-001")
    assert r.status == "cancelled" and r.fulfilled == 1
