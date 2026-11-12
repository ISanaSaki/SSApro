import pytest

from app.data.models import Event, Notification


def wave_notification(request_id, donor_id):
    return Notification(notification_id="nt-w-" + donor_id, request_id=request_id,
                        donor_id=donor_id, template="request_wave", created_sim_min=100.0,
                        sent_sim_min=100.0, gateway_status=None, response=None)


def accepted_event(request_id, donor_id, event_id):
    return Event(event_id=event_id, request_id=request_id, donor_id=donor_id,
                 notification_id="nt-x", kind="donor_response", response="accepted",
                 event=None, status=None, reason=None, sim_time=1.0, received_at_sim_min=100.0)


def donated_event(request_id, donor_id, event_id):
    return Event(event_id=event_id, request_id=request_id, donor_id=donor_id,
                 notification_id="nt-x", kind="donor_progress", response=None,
                 event="donated", status=None, reason=None, sim_time=1.0,
                 received_at_sim_min=100.0)


def arrived_event(request_id, donor_id, event_id):
    return Event(event_id=event_id, request_id=request_id, donor_id=donor_id,
                 notification_id="nt-x", kind="donor_progress", response=None,
                 event="arrived", status=None, reason=None, sim_time=1.0,
                 received_at_sim_min=100.0)


# ---------------------------------------------------------------- recheck filters


@pytest.mark.asyncio
async def test_recheck_excluded(services, make_donor):
    donor = make_donor(permanently_excluded=1)
    assert services.invitation.recheck(donor, "red_cells", "O+", 100.0) is False
    assert services.invitation.recheck(make_donor("D2"), "red_cells", "O+", 100.0) is True


@pytest.mark.asyncio
async def test_recheck_age_bounds(services, make_donor):
    assert services.invitation.recheck(make_donor("D1", age=17), "red_cells", "O+", 100.0) is False
    assert services.invitation.recheck(make_donor("D2", age=66), "red_cells", "O+", 100.0) is False
    assert services.invitation.recheck(make_donor("D3", age=18), "red_cells", "O+", 100.0) is True
    assert services.invitation.recheck(make_donor("D4", age=65), "red_cells", "O+", 100.0) is True


@pytest.mark.asyncio
async def test_recheck_weight(services, make_donor):
    assert services.invitation.recheck(make_donor("D1", weight_kg=49.9), "red_cells", "O+",
                                       100.0) is False
    assert services.invitation.recheck(make_donor("D2", weight_kg=50.0), "red_cells", "O+",
                                       100.0) is True


@pytest.mark.asyncio
async def test_recheck_deferral(services, make_donor):
    donor = make_donor(defer_until="2027-01-15T05:00:00")  # 300 sim min
    assert services.invitation.recheck(donor, "red_cells", "O+", 100.0) is False
    assert services.invitation.recheck(donor, "red_cells", "O+", 301.0) is True


@pytest.mark.asyncio
async def test_recheck_donation_interval(services, make_donor):
    recent = make_donor("D1", last_donation_at="2027-01-10T00:00:00",
                        last_donation_type="whole_blood")
    assert services.invitation.recheck(recent, "red_cells", "O+", 100.0) is False  # 5d < 60d
    old = make_donor("D2", last_donation_at="2026-11-01T00:00:00",
                     last_donation_type="whole_blood")
    assert services.invitation.recheck(old, "red_cells", "O+", 100.0) is True  # ~75d >= 60d
    female = make_donor("D3", sex="F", last_donation_at="2026-11-01T00:00:00",
                        last_donation_type="whole_blood")
    assert services.invitation.recheck(female, "red_cells", "O+", 100.0) is False  # 75d < 90d
    recent_plat = make_donor("D4", last_donation_at="2027-01-10T00:00:00",
                             last_donation_type="platelets")
    assert services.invitation.recheck(recent_plat, "platelets", "O+", 100.0) is False  # 5d < 14d
    cross = make_donor("D5", last_donation_at="2027-01-10T00:00:00",
                       last_donation_type="whole_blood")
    assert services.invitation.recheck(cross, "platelets", "O+", 100.0) is False  # cross_block
    assert services.invitation.recheck(make_donor("D6"), "red_cells", "O+", 100.0) is True


@pytest.mark.asyncio
async def test_recheck_quiet_hours(services, make_donor):
    day = make_donor("D1", quiet_start_hour=2, quiet_end_hour=5)
    assert services.invitation.recheck(day, "red_cells", "O+", 180.0) is False  # hour 3
    assert services.invitation.recheck(day, "red_cells", "O+", 360.0) is True  # hour 6
    night = make_donor("D2", quiet_start_hour=22, quiet_end_hour=2)
    assert services.invitation.recheck(night, "red_cells", "O+", 1380.0) is False  # hour 23
    assert services.invitation.recheck(night, "red_cells", "O+", 60.0) is False  # hour 1
    assert services.invitation.recheck(night, "red_cells", "O+", 720.0) is True  # hour 12
    none = make_donor("D3", quiet_start_hour=5, quiet_end_hour=5)
    assert services.invitation.recheck(none, "red_cells", "O+", 300.0) is True  # hour 5


@pytest.mark.asyncio
async def test_recheck_compat(services, make_donor):
    assert services.invitation.recheck(make_donor("D1", blood_group="B+"), "red_cells", "O+",
                                       100.0) is False
    assert services.invitation.recheck(make_donor("D2", blood_group="O-"), "red_cells", "O+",
                                       100.0) is True


# ---------------------------------------------------------------- build_wave


@pytest.mark.asyncio
async def test_wave_sends_only_to_eligible(services, make_request, make_donor, gateway, repos):
    make_request()  # R-001: red_cells O+, needed 4
    make_donor("D1", permanently_excluded=1)
    make_donor("D2", age=17)
    make_donor("D3", defer_until="2027-01-15T05:00:00")
    make_donor("D4", quiet_start_hour=2, quiet_end_hour=5)
    make_donor("D5", blood_group="B+")
    make_donor("D6")
    sent = await services.invitation.build_wave("R-001", 180.0)
    assert sent == 1
    assert [m["donor_id"] for m in gateway.messages] == ["D6"]
    r = await repos.request.get("R-001")
    assert r.status == "mobilizing" and r.wave_count == 1


@pytest.mark.asyncio
async def test_wave_respects_min_cap(services, make_request, make_donor, gateway, repos):
    make_request()
    for i in range(50):
        make_donor(f"D{i:02d}")
    sent = await services.invitation.build_wave("R-001", 100.0)
    assert sent == 24
    assert len(gateway.messages) == 24
    r = await repos.request.get("R-001")
    assert r.status == "mobilizing"


@pytest.mark.asyncio
async def test_wave_skips_already_notified(services, make_request, make_donor, store, repos):
    make_request()
    make_donor()
    store.notifications.append(wave_notification("R-001", "D00001"))
    sent = await services.invitation.build_wave("R-001", 100.0)
    assert sent == 0
    r = await repos.request.get("R-001")
    assert r.wave_count == 1 and r.status == "open"


@pytest.mark.asyncio
async def test_wave_terminal_noop(services, make_request, make_donor, gateway):
    make_request(status="fulfilled")
    make_donor()
    assert await services.invitation.build_wave("R-001", 100.0) == 0
    assert gateway.messages == []


@pytest.mark.asyncio
async def test_wave_disabled_outreach(services, make_request, make_donor, gateway, settings):
    make_request()
    make_donor()
    settings.disable_outreach = True
    assert await services.invitation.build_wave("R-001", 100.0) == 0
    assert gateway.messages == []


@pytest.mark.asyncio
async def test_wave_shortage_covered_by_stock(services, make_request, make_donor, gateway):
    make_request(stock_inflight=4)
    make_donor()
    assert await services.invitation.build_wave("R-001", 100.0) == 0
    assert gateway.messages == []


# ---------------------------------------------------------------- stop_outreach / reminders


@pytest.mark.asyncio
async def test_stop_outreach_notifies_accepted_not_donated(services, make_request, store, gateway):
    make_request()
    store.notifications.append(wave_notification("R-001", "D1"))
    store.notifications.append(wave_notification("R-001", "D2"))
    store.events.append(accepted_event("R-001", "D1", "ev-a1"))
    store.events.append(accepted_event("R-001", "D2", "ev-a2"))
    store.events.append(donated_event("R-001", "D2", "ev-do"))
    sent = await services.invitation.stop_outreach("R-001", "not_needed")
    assert sent == 1
    assert gateway.messages[0]["template"] == "not_needed"
    assert gateway.messages[0]["donor_id"] == "D1"


@pytest.mark.asyncio
async def test_reminders_skip_arrived(services, make_request, store, gateway):
    make_request()
    store.notifications.append(wave_notification("R-001", "D1"))
    store.notifications.append(wave_notification("R-001", "D2"))
    store.events.append(accepted_event("R-001", "D1", "ev-a1"))
    store.events.append(accepted_event("R-001", "D2", "ev-a2"))
    store.events.append(arrived_event("R-001", "D1", "ev-ar"))
    sent = await services.invitation.send_reminders("R-001", 200.0)
    assert sent == 1
    assert gateway.messages[0]["template"] == "reminder"
    assert gateway.messages[0]["donor_id"] == "D2"
