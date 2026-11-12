import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
import yaml
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.data.database import create_all
from app.data.models import Dispatch, Event, Notification, Request, Task

MINI_RULES = {
    "version": 1,
    "age_min": 18,
    "age_max": 65,
    "weight_min_kg": 50,
    "interval_wb_male": 60,
    "interval_wb_female": 90,
    "interval_apheresis": 14,
    "cross_block": 14,
    "event_deferral": {"tattoo": 180, "travel_risk": 90},
    "sla": {"critical": 90, "urgent": 240, "planned": 1440},
    "shelf_days": {"red_cells": 42, "platelets": 5, "plasma": 365},
    "proc_min": 20,
    "visit_min": {"red_cells": 20, "platelets": 90, "plasma": 45},
}

MINI_COMPAT = {
    "red_cells": {"O+": ["O+", "O-"]},
    "plasma": {"AB+": ["AB+", "AB-"]},
}

DONOR_HEADER = [
    "donor_id", "blood_group", "sex", "age", "weight_kg", "lat", "lon", "area_id",
    "quiet_start_hour", "quiet_end_hour", "last_donation_at", "last_donation_type",
    "permanently_excluded", "notified_90d",
]


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    await create_all(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def mini_kit(tmp_path: Path) -> Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    donors = [
        ["D_ok", "O+", "F", 30, 60.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_excluded", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 1, 0],
        ["D_age_low", "O+", "M", 17, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_age_high", "O+", "M", 66, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_weight", "O+", "M", 30, 49.9, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_defer_active", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_defer_past", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_group", "A+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_quiet", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 10, 12, "", "", 0, 0],
        ["D_quiet_wrap", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 2, "", "", 0, 0],
        ["D_interval_recent", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7,
         "2026-12-16T00:00:00", "red_cells", 0, 0],
        ["D_interval_ok", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7,
         "2026-11-15T00:00:00", "red_cells", 0, 0],
        ["D_cross_recent", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7,
         "2027-01-05T00:00:00", "plasma", 0, 0],
        ["D_female_60", "O+", "F", 30, 70.0, 33.0, 51.0, "A1", 22, 7,
         "2026-11-15T00:00:00", "red_cells", 0, 0],
        ["D_female_ok", "O+", "F", 30, 70.0, 33.0, 51.0, "A1", 22, 7,
         "2026-10-16T00:00:00", "red_cells", 0, 0],
        ["D_invited", "O+", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
        ["D_hist", "O-", "M", 30, 70.0, 33.0, 51.0, "A1", 22, 7, "", "", 0, 0],
    ]
    _write_csv(kit / "donors.csv", DONOR_HEADER, donors)
    _write_csv(
        kit / "hospitals.csv",
        ["hospital_id", "name", "lat", "lon", "request_weight", "credit_level"],
        [
            ["H01", "Hospital One", 33.7, 51.0, 0.9, "high"],
            ["H02", "Hospital Two", 33.8, 51.1, 0.5, "medium"],
        ],
    )
    _write_csv(
        kit / "centers.csv",
        ["center_id", "name", "lat", "lon", "beds", "open_hour", "close_hour"],
        [
            ["MC1", "Center One", 33.7, 51.0, 12, 0, 24],
            ["MC2", "Center Two", 33.9, 51.2, 8, 8, 20],
        ],
    )
    _write_csv(
        kit / "donor_events.csv",
        ["donor_id", "event", "event_at", "defer_days", "defer_until"],
        [
            ["D_defer_active", "tattoo", "2027-01-01T00:00:00", 180, "2027-06-30T00:00:00"],
            ["D_defer_active", "travel_risk", "2027-02-01T00:00:00", 90, "2027-05-02T00:00:00"],
            ["D_defer_past", "tattoo", "2026-06-01T00:00:00", 180, "2026-11-28T00:00:00"],
        ],
    )
    history = kit / "history"
    history.mkdir()
    _write_csv(
        history / "responses.csv",
        ["request_id", "donor_id", "notified_at", "wave", "responded", "accepted",
         "response_delay_min", "arrived", "donated"],
        [
            ["RH000001", "D_hist", "2026-01-15T08:00:00", 1, 1, 1, 10.0, 1, 1],
            ["RH000002", "D_hist", "2026-02-15T08:00:00", 1, 1, 0, 20.0, 0, 0],
            ["RH000003", "D_hist", "2026-03-15T08:00:00", 2, 0, 0, "", 0, 0],
            ["RH000004", "D_hist", "2026-04-15T08:00:00", 2, 1, 1, 30.0, 1, 0],
        ],
    )
    _write_csv(
        kit / "travel_area_to_hospital.csv",
        ["area_id", "H01", "H02"],
        [["A1", 10.5, 20.0], ["A2", 30.0, 40.0]],
    )
    _write_csv(
        kit / "travel_area_to_center.csv",
        ["area_id", "MC1", "MC2"],
        [["A1", 5.0, 6.0]],
    )
    _write_csv(
        kit / "travel_center_to_hospital.csv",
        ["center_id", "H01", "H02"],
        [["MC1", 7.5, 8.5]],
    )
    with (kit / "compat.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(MINI_COMPAT, fh, sort_keys=False)
    with (kit / "rules.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(MINI_RULES, fh, sort_keys=False)
    return kit


@pytest.fixture
def kit_settings(mini_kit):
    return SimpleNamespace(KIT_PATH=str(mini_kit))


def make_request(idempotency_key: str = "k1", **overrides) -> Request:
    data = dict(
        id="R-000000000001",
        hospital_id="H01",
        blood_group="O+",
        product="red_cells",
        units=2,
        urgency="critical",
        note=None,
        status="pending_review",
        needed=2,
        created_sim_min=0.0,
        updated_sim_min=0.0,
        sla_deadline_sim_min=90.0,
        idempotency_key=idempotency_key,
        idempotency_body_hash="hash-1",
    )
    data.update(overrides)
    return Request(**data)


def make_event(event_id: str = "ev-1", **overrides) -> Event:
    data = dict(
        event_id=event_id,
        request_id="R-000000000001",
        donor_id="D00001",
        notification_id=None,
        kind="donor_progress",
        event="en_route",
        sim_time=1.0,
        received_at_sim_min=1.0,
    )
    data.update(overrides)
    return Event(**data)


def make_dispatch(dispatch_id: str = "dsp-1", **overrides) -> Dispatch:
    data = dict(
        dispatch_id=dispatch_id,
        request_id="R-000000000001",
        center_id="MC1",
        blood_group="O-",
        product="red_cells",
        units=1,
        hospital_id="H01",
        recipient_blood_group="O+",
        created_sim_min=1.0,
        delivery_sim_min=30.0,
    )
    data.update(overrides)
    return Dispatch(**data)


def make_notification(notification_id: str = "nt-1", **overrides) -> Notification:
    data = dict(
        notification_id=notification_id,
        request_id="R-000000000001",
        donor_id="D00001",
        template="request_wave",
        created_sim_min=1.0,
    )
    data.update(overrides)
    return Notification(**data)


def make_task(**overrides) -> Task:
    data = dict(
        task_type="send_wave",
        request_id="R-000000000001",
        payload_json="{}",
        created_sim_min=0.0,
        next_attempt_sim_min=10.0,
    )
    data.update(overrides)
    return Task(**data)
