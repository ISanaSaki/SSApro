import pytest

from app.data.loader import load_kit_data
from app.data.repositories import (
    CenterRepository,
    DispatchRepository,
    DonorRepository,
    EventRepository,
    HospitalRepository,
    NotificationRepository,
    RequestRepository,
    TaskRepository,
)

from conftest import (
    MINI_COMPAT,
    MINI_RULES,
    make_dispatch,
    make_event,
    make_notification,
    make_request,
    make_task,
)

RID = "R-000000000001"


class TestRequestRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session_maker):
        async with session_maker() as session:
            repo = RequestRepository(session)
            req = make_request(idempotency_key="key-a")
            created = await repo.create(req)
            assert created is not None
            fetched = await repo.get(RID)
            assert fetched is created
            assert (await repo.get_by_idempotency_key("key-a")) is created

    @pytest.mark.asyncio
    async def test_create_duplicate_key_returns_none(self, session_maker):
        async with session_maker() as session:
            repo = RequestRepository(session)
            assert await repo.create(make_request(idempotency_key="key-dup")) is not None
            conflict = await repo.create(
                make_request(id="R-000000000002", idempotency_key="key-dup")
            )
            assert conflict is None
            await session.commit()

    @pytest.mark.asyncio
    async def test_list_filters(self, session_maker):
        async with session_maker() as session:
            repo = RequestRepository(session)
            await repo.create(make_request(idempotency_key="key-1", hospital_id="H01"))
            await repo.create(
                make_request(
                    id="R-000000000002", idempotency_key="key-2", hospital_id="H02",
                    created_sim_min=5.0,
                )
            )
            await repo.create(
                make_request(
                    id="R-000000000003", idempotency_key="key-3", hospital_id="H01",
                    status="open", created_sim_min=10.0,
                )
            )
            all_requests = await repo.list()
            h01_requests = await repo.list(hospital_id="H01")
            open_requests = await repo.list(status="open")
            assert len(all_requests) == 3
            assert [r.id for r in all_requests] == [
                "R-000000000003",
                "R-000000000002",
                "R-000000000001",
            ]
            assert {r.id for r in h01_requests} == {"R-000000000001", "R-000000000003"}
            assert [r.id for r in open_requests] == ["R-000000000003"]

    @pytest.mark.asyncio
    async def test_update(self, session_maker):
        async with session_maker() as session:
            repo = RequestRepository(session)
            await repo.create(make_request(idempotency_key="key-upd"))
            fetched = await repo.get(RID)
            fetched.status = "open"
            fetched.confirmed = 3
            await repo.update(fetched)
            refetched = await repo.get(RID)
            assert refetched.status == "open"
            assert refetched.confirmed == 3


class TestEventRepository:
    @pytest.mark.asyncio
    async def test_add_or_ignore_and_exists(self, session_maker):
        async with session_maker() as session:
            repo = EventRepository(session)
            assert await repo.add_or_ignore(make_event(event_id="ev-a")) is True
            assert await repo.exists("ev-a") is True
            assert await repo.exists("ev-b") is False

    @pytest.mark.asyncio
    async def test_duplicate_event_ignored_and_commit_clean(self, session_maker):
        async with session_maker() as session:
            repo = EventRepository(session)
            assert await repo.add_or_ignore(make_event(event_id="ev-dup")) is True
            assert await repo.add_or_ignore(make_event(event_id="ev-dup")) is False
            await session.commit()
            assert await repo.exists("ev-dup") is True

    @pytest.mark.asyncio
    async def test_count_for(self, session_maker):
        async with session_maker() as session:
            repo = EventRepository(session)
            await repo.add_or_ignore(
                make_event(
                    event_id="ev-d1", kind="donor_progress", event="donated",
                    donor_id="D00001", received_at_sim_min=1.0,
                )
            )
            await repo.add_or_ignore(
                make_event(
                    event_id="ev-d2", kind="donor_progress", event="donated",
                    donor_id="D00001", received_at_sim_min=2.0,
                )
            )
            await repo.add_or_ignore(
                make_event(
                    event_id="ev-e1", kind="donor_progress", event="en_route",
                    donor_id="D00002", received_at_sim_min=3.0,
                )
            )
            assert await repo.count_for(RID, "donor_progress", "event", "donated", "D00001") == 2
            assert await repo.count_for(RID, "donor_progress", "event", "en_route", "D00001") == 0
            with pytest.raises(ValueError):
                await repo.count_for(RID, "donor_progress", "reason", "x", "D00001")

    @pytest.mark.asyncio
    async def test_list_for_request_ordered(self, session_maker):
        async with session_maker() as session:
            repo = EventRepository(session)
            await repo.add_or_ignore(make_event(event_id="ev-1", received_at_sim_min=5.0))
            await repo.add_or_ignore(make_event(event_id="ev-2", received_at_sim_min=1.0))
            events = await repo.list_for_request(RID)
            assert [e.event_id for e in events] == ["ev-2", "ev-1"]


class TestDispatchRepository:
    @pytest.mark.asyncio
    async def test_add_or_ignore_duplicate(self, session_maker):
        async with session_maker() as session:
            repo = DispatchRepository(session)
            assert await repo.add_or_ignore(make_dispatch(dispatch_id="dsp-dup")) is True
            assert await repo.add_or_ignore(make_dispatch(dispatch_id="dsp-dup")) is False
            await session.commit()

    @pytest.mark.asyncio
    async def test_due_deliveries(self, session_maker):
        async with session_maker() as session:
            repo = DispatchRepository(session)
            await repo.add_or_ignore(
                make_dispatch(dispatch_id="dsp-due", delivery_sim_min=30.0)
            )
            await repo.add_or_ignore(
                make_dispatch(dispatch_id="dsp-later", delivery_sim_min=31.0)
            )
            await repo.add_or_ignore(
                make_dispatch(dispatch_id="dsp-failed", outcome="failed", delivery_sim_min=1.0)
            )
            due = await repo.due_deliveries(30.0)
            assert [d.dispatch_id for d in due] == ["dsp-due"]


class TestNotificationRepository:
    @pytest.mark.asyncio
    async def test_add_get_find(self, session_maker):
        async with session_maker() as session:
            repo = NotificationRepository(session)
            await repo.add(make_notification(notification_id="nt-a", donor_id="D00001"))
            assert (await repo.get("nt-a")).notification_id == "nt-a"
            assert (await repo.get("nt-b")) is None
            assert (await repo.find(RID, "D00001")).notification_id == "nt-a"
            assert await repo.find(RID, "D00009") is None

    @pytest.mark.asyncio
    async def test_accepted_not_donated(self, session_maker):
        async with session_maker() as session:
            notif_repo = NotificationRepository(session)
            event_repo = EventRepository(session)
            await notif_repo.add(
                make_notification(notification_id="nt-1", donor_id="D1", response="accepted")
            )
            await notif_repo.add(
                make_notification(notification_id="nt-2", donor_id="D2", response="accepted")
            )
            await notif_repo.add(
                make_notification(notification_id="nt-3", donor_id="D3", response="declined")
            )
            await event_repo.add_or_ignore(
                make_event(event_id="ev-don", donor_id="D2", event="donated", kind="donor_progress")
            )
            accepted = await notif_repo.accepted_not_donated(RID)
            assert [n.donor_id for n in accepted] == ["D1"]


class TestDonorRepository:
    @pytest.mark.asyncio
    async def test_eligible_full_filter_set(self, engine, kit_settings, session_maker):
        await load_kit_data(kit_settings, engine)
        async with session_maker() as session:
            repo = DonorRepository(session)
            eligible = await repo.eligible(
                "red_cells", "O+", "R-test1", 600.0, MINI_RULES, MINI_COMPAT
            )
            eligible_ids = {d.donor_id for d in eligible}
            assert eligible_ids == {
                "D_ok",
                "D_defer_past",
                "D_quiet_wrap",
                "D_interval_ok",
                "D_female_ok",
                "D_invited",
                "D_hist",
            }

    @pytest.mark.asyncio
    async def test_eligible_excludes_already_invited(self, engine, kit_settings, session_maker):
        await load_kit_data(kit_settings, engine)
        async with session_maker() as session:
            notif_repo = NotificationRepository(session)
            await notif_repo.add(
                make_notification(notification_id="nt-inv", donor_id="D_ok", request_id="R-test1")
            )
            repo = DonorRepository(session)
            eligible = await repo.eligible(
                "red_cells", "O+", "R-test1", 600.0, MINI_RULES, MINI_COMPAT
            )
            assert "D_ok" not in {d.donor_id for d in eligible}
            eligible_other_request = await repo.eligible(
                "red_cells", "O+", "R-other", 600.0, MINI_RULES, MINI_COMPAT
            )
            assert "D_ok" in {d.donor_id for d in eligible_other_request}

    @pytest.mark.asyncio
    async def test_eligible_unknown_compat_returns_empty(self, engine, kit_settings, session_maker):
        await load_kit_data(kit_settings, engine)
        async with session_maker() as session:
            repo = DonorRepository(session)
            eligible = await repo.eligible(
                "red_cells", "B-", "R-test1", 600.0, MINI_RULES, MINI_COMPAT
            )
            assert eligible == []

    @pytest.mark.asyncio
    async def test_history_features(self, engine, kit_settings, session_maker):
        await load_kit_data(kit_settings, engine)
        async with session_maker() as session:
            repo = DonorRepository(session)
            features = await repo.history_features("D_hist")
        assert features["notified_count"] == 4
        assert features["responded_count"] == 3
        assert features["accepted_count"] == 2
        assert features["donated_count"] == 1
        assert features["response_rate"] == pytest.approx(0.75)
        assert features["accept_rate"] == pytest.approx(0.5)
        assert features["donate_rate"] == pytest.approx(0.25)
        assert features["mean_response_delay_min"] == pytest.approx(20.0)


class TestTaskRepository:
    @pytest.mark.asyncio
    async def test_pop_due_filters_and_orders(self, session_maker):
        async with session_maker() as session:
            repo = TaskRepository(session)
            await repo.push(make_task(next_attempt_sim_min=20.0))
            await repo.push(make_task(next_attempt_sim_min=5.0))
            await repo.push(make_task(next_attempt_sim_min=10.0))
            due = await repo.pop_due(10.0, limit=10)
            assert [t.next_attempt_sim_min for t in due] == [5.0, 10.0]
            limited = await repo.pop_due(100.0, limit=1)
            assert len(limited) == 1
            # CONTRACT orders pop_due by task id, not by due time.
            assert limited[0].next_attempt_sim_min == 20.0

    @pytest.mark.asyncio
    async def test_finish(self, session_maker):
        async with session_maker() as session:
            repo = TaskRepository(session)
            task = make_task()
            await repo.push(task)
            await session.flush()
            task_id = task.id
            await repo.finish(task_id, ok=True)
            await repo.finish(99999, ok=False)
            done = await repo.pop_due(1000.0, limit=10)
            assert all(t.id != task_id for t in done)
            from app.data.models import Task

            finished = await session.get(Task, task_id)
            assert finished.status == "done"


class TestHospitalAndCenterRepositories:
    @pytest.mark.asyncio
    async def test_hospital_exists_and_list(self, engine, kit_settings, session_maker):
        await load_kit_data(kit_settings, engine)
        async with session_maker() as session:
            repo = HospitalRepository(session)
            assert await repo.exists("H01") is True
            assert await repo.exists("H98") is False
            hospitals = await repo.list()
            assert [h.hospital_id for h in hospitals] == ["H01", "H02"]

    @pytest.mark.asyncio
    async def test_center_list(self, engine, kit_settings, session_maker):
        await load_kit_data(kit_settings, engine)
        async with session_maker() as session:
            centers = await CenterRepository(session).list()
            assert [c.center_id for c in centers] == ["MC1", "MC2"]
