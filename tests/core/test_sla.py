import pytest

from app.data.models import Event, Notification

from test_callbacks import wave_notification  # noqa: F401  (reuse helper)


def accepted_event(request_id, donor_id, event_id):
    return Event(event_id=event_id, request_id=request_id, donor_id=donor_id,
                 notification_id="nt-x", kind="donor_response", response="accepted",
                 event=None, status=None, reason=None, sim_time=1.0, received_at_sim_min=100.0)


@pytest.mark.asyncio
async def test_expires_at_deadline(services, make_request, repos, store, gateway):
    make_request(status="open", sla_deadline_sim_min=100.0)
    store.notifications.append(wave_notification("R-001", "D1"))
    store.events.append(accepted_event("R-001", "D1", "ev-a1"))
    expired = await services.sla.check_expired(100.0)
    assert expired == ["R-001"]
    r = await repos.request.get("R-001")
    assert r.status == "expired"
    cancelled = [m for m in gateway.messages if m["template"] == "cancelled"]
    assert len(cancelled) == 1 and cancelled[0]["donor_id"] == "D1"


@pytest.mark.asyncio
async def test_open_before_deadline_untouched(services, make_request, repos):
    make_request(status="open", sla_deadline_sim_min=200.0)
    assert await services.sla.check_expired(100.0) == []
    r = await repos.request.get("R-001")
    assert r.status == "open"


@pytest.mark.asyncio
async def test_pending_review_not_expired(services, make_request, repos, gateway):
    make_request(status="pending_review", sla_deadline_sim_min=100.0)
    assert await services.sla.check_expired(100.0) == []
    assert gateway.messages == []


@pytest.mark.asyncio
async def test_terminal_not_expired(services, make_request, repos):
    for status in ("fulfilled", "cancelled", "expired"):
        make_request(f"R-{status}", status=status, sla_deadline_sim_min=100.0)
    assert await services.sla.check_expired(100.0) == []
    r = await repos.request.get("R-fulfilled")
    assert r.status == "fulfilled"


@pytest.mark.asyncio
async def test_amend_resets_deadline(services, make_request, repos, kit):
    make_request(status="open")
    result = await services.request.amend_urgency("R-001", "planned", 100.0)
    assert result == {"request_id": "R-001", "urgency": "planned"}
    r = await repos.request.get("R-001")
    assert r.sla_deadline_sim_min == 100.0 + kit.rules["sla"]["planned"]


@pytest.mark.asyncio
async def test_amend_terminal_rejected(services, make_request):
    make_request(status="cancelled")
    result = await services.request.amend_urgency("R-001", "planned", 100.0)
    assert result.code == "not_amendable" and result.http_status == 409
