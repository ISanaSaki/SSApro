"""Shared test doubles for DEV-01 tests.

The real `app/data` layer (DEV-02) does not exist yet, so this module installs an
in-memory stand-in under the exact frozen names (CONTRACT section 8.1) into
sys.modules before any `app.*` import happens. When the real layer lands, the shim
detects it and stays out of the way.
"""

import csv
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from sqlalchemy.exc import IntegrityError

BASE = Path(__file__).resolve().parents[2]
KIT_DIR = BASE / "participant_kit"

# ---------------------------------------------------------------- model doubles


class Request:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Event:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Dispatch:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Notification:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Donor:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Hospital:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Center:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Task:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------- in-memory store


class Store:
    def __init__(self):
        self.requests = {}
        self.events = []
        self.dispatches = {}
        self.notifications = []
        self.donors = {}
        self.hospitals = {}
        self.centers = {}
        self.tasks = {}
        self.task_seq = 0


_STORE = None


def set_store(store: Store) -> None:
    global _STORE
    _STORE = store


def _store() -> Store:
    assert _STORE is not None, "store fixture must run first"
    return _STORE


# ---------------------------------------------------------------- repository fakes


class RequestRepository:
    def __init__(self, session):
        pass

    async def create(self, req: Request) -> Request:
        s = _store()
        for r in s.requests.values():
            if r.idempotency_key == req.idempotency_key:
                raise IntegrityError("UNIQUE constraint failed: requests.idempotency_key", {},
                                     Exception("unique"))
        s.requests[req.id] = req
        return req

    async def get(self, request_id: str):
        return _store().requests.get(request_id)

    async def get_by_idempotency_key(self, key: str):
        return next((r for r in _store().requests.values() if r.idempotency_key == key), None)

    async def list(self, hospital_id: str | None = None, status: str | None = None):
        out = list(_store().requests.values())
        if hospital_id:
            out = [r for r in out if r.hospital_id == hospital_id]
        if status:
            out = [r for r in out if r.status == status]
        return out

    async def update(self, req: Request) -> None:
        _store().requests[req.id] = req


class EventRepository:
    def __init__(self, session):
        pass

    async def add_or_ignore(self, ev: Event) -> bool:
        s = _store()
        if any(e.event_id == ev.event_id for e in s.events):
            return False
        s.events.append(ev)
        return True

    async def exists(self, event_id: str) -> bool:
        return any(e.event_id == event_id for e in _store().events)

    async def count_for(self, request_id: str, kind: str, field: str, value: str,
                        donor_id: str) -> int:
        return sum(1 for e in _store().events
                   if e.request_id == request_id and e.kind == kind and e.donor_id == donor_id
                   and getattr(e, field, None) == value)

    async def list_for_request(self, request_id: str):
        return [e for e in _store().events if e.request_id == request_id]


class DispatchRepository:
    def __init__(self, session):
        pass

    async def add_or_ignore(self, d: Dispatch) -> bool:
        s = _store()
        if d.dispatch_id in s.dispatches:
            return False
        s.dispatches[d.dispatch_id] = d
        return True

    async def list_for_request(self, request_id: str):
        return [d for d in _store().dispatches.values() if d.request_id == request_id]

    async def due_deliveries(self, sim_min: float):
        return [d for d in _store().dispatches.values()
                if d.outcome == "created" and d.delivery_sim_min <= sim_min]


class NotificationRepository:
    def __init__(self, session):
        pass

    async def add(self, n: Notification) -> None:
        s = _store()
        if any(x.notification_id == n.notification_id for x in s.notifications):
            return
        s.notifications.append(n)

    async def get(self, notification_id: str):
        return next((n for n in _store().notifications
                     if n.notification_id == notification_id), None)

    async def find(self, request_id: str, donor_id: str):
        return next((n for n in _store().notifications
                     if n.request_id == request_id and n.donor_id == donor_id), None)

    async def list_for_request(self, request_id: str):
        return [n for n in _store().notifications if n.request_id == request_id]

    async def accepted_not_donated(self, request_id: str):
        s = _store()
        accepted = {e.donor_id for e in s.events
                    if e.request_id == request_id and e.kind == "donor_response"
                    and e.response == "accepted"}
        donated = {e.donor_id for e in s.events
                   if e.request_id == request_id and e.kind == "donor_progress"
                   and e.event == "donated"}
        return [n for n in s.notifications
                if n.request_id == request_id and n.template == "request_wave"
                and n.donor_id in accepted and n.donor_id not in donated]


class DonorRepository:
    def __init__(self, session):
        pass

    async def get(self, donor_id: str):
        return _store().donors.get(donor_id)

    async def eligible(self, product: str, recipient_group: str, request_id: str,
                       sim_min: float, rules: dict, compat: dict):
        # Deliberately loose (compatibility only): InvitationService.recheck must
        # enforce the remaining safety filters. This proves the defense-in-depth layer.
        allowed = compat.get(product, {}).get(recipient_group, [])
        return [d for d in _store().donors.values() if d.blood_group in allowed]

    async def history_features(self, donor_id: str) -> dict:
        return {}


class TaskRepository:
    def __init__(self, session):
        pass

    async def push(self, task: Task) -> None:
        s = _store()
        s.task_seq += 1
        task.id = s.task_seq
        s.tasks[task.id] = task

    async def pop_due(self, sim_min: float, limit: int):
        due = sorted([t for t in _store().tasks.values()
                      if t.status == "pending" and t.next_attempt_sim_min <= sim_min],
                     key=lambda t: t.id)
        return due[:limit]

    async def finish(self, task_id: int, ok: bool) -> None:
        t = _store().tasks.get(task_id)
        if t is not None:
            t.status = "done" if ok else "failed"


class HospitalRepository:
    def __init__(self, session):
        pass

    async def exists(self, hospital_id: str) -> bool:
        return hospital_id in _store().hospitals

    async def list(self):
        return list(_store().hospitals.values())


class CenterRepository:
    def __init__(self, session):
        pass

    async def list(self):
        return list(_store().centers.values())


# ---------------------------------------------------------------- app.data shim

_KIT = None


@dataclass
class KitData:
    compat: dict
    rules: dict
    travel_area_to_hospital: dict
    travel_center_to_hospital: dict
    travel_area_to_center: dict
    epoch: datetime


def _read_travel(filename: str) -> dict:
    out = {}
    with open(KIT_DIR / filename, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = row.pop("area_id", None) or row.pop("center_id", None)
            for dest, value in row.items():
                try:
                    out[(key, dest)] = float(value)
                except ValueError:
                    pass
    return out


def build_kit() -> KitData:
    global _KIT
    if _KIT is not None:
        return _KIT
    rules = yaml.safe_load((KIT_DIR / "rules.yaml").read_text(encoding="utf-8"))
    compat = yaml.safe_load((KIT_DIR / "compat.yaml").read_text(encoding="utf-8"))
    _KIT = KitData(
        compat=compat,
        rules=rules,
        travel_area_to_hospital=_read_travel("travel_area_to_hospital.csv"),
        travel_center_to_hospital=_read_travel("travel_center_to_hospital.csv"),
        travel_area_to_center=_read_travel("travel_area_to_center.csv"),
        epoch=datetime(2027, 1, 15, 0, 0),
    )
    return _KIT


def _install_data_shim() -> None:
    try:
        import app.data  # noqa: F401
        return
    except ImportError:
        pass

    app_data = types.ModuleType("app.data")
    app_data.__path__ = []
    sys.modules["app.data"] = app_data

    models = types.ModuleType("app.data.models")
    for name in ("Request", "Event", "Dispatch", "Notification", "Donor", "Hospital",
                 "Center", "Task"):
        setattr(models, name, globals()[name])
    sys.modules["app.data.models"] = models
    setattr(app_data, "models", models)

    database = types.ModuleType("app.data.database")

    def init_engine(settings):
        from sqlalchemy.ext.asyncio import create_async_engine
        return create_async_engine("sqlite+aiosqlite:///:memory:")

    async def create_all(engine):
        return None

    def get_session():
        async def _gen():
            yield None
        return _gen()

    database.init_engine = init_engine
    database.create_all = create_all
    database.get_session = get_session
    sys.modules["app.data.database"] = database
    setattr(app_data, "database", database)

    loader = types.ModuleType("app.data.loader")

    async def load_kit_data(settings, engine):
        return build_kit()

    loader.load_kit_data = load_kit_data
    loader.KitData = KitData
    sys.modules["app.data.loader"] = loader
    setattr(app_data, "loader", loader)

    repos = types.ModuleType("app.data.repositories")
    for name in ("RequestRepository", "EventRepository", "DispatchRepository",
                 "NotificationRepository", "DonorRepository", "TaskRepository",
                 "HospitalRepository", "CenterRepository"):
        setattr(repos, name, globals()[name])
    repos.set_store = set_store
    sys.modules["app.data.repositories"] = repos
    setattr(app_data, "repositories", repos)


_install_data_shim()

from app.config import Settings  # noqa: E402
from app.domain.ranking import TravelTimeRankingStrategy  # noqa: E402
from app.ports.clients import DispatchResult, SendResult  # noqa: E402
from app.services.allocation_service import AllocationService  # noqa: E402
from app.services.callback_processor import CallbackProcessor  # noqa: E402
from app.services.invitation_service import InvitationService  # noqa: E402
from app.services.request_service import RequestService  # noqa: E402
from app.services.sla_service import SlaService  # noqa: E402

# ---------------------------------------------------------------- port fakes


class FakeClock:
    def __init__(self, sim: float = 0.0):
        self.sim = sim

    def set(self, sim: float) -> None:
        self.sim = sim

    async def now_sim(self) -> float:
        return self.sim

    async def payload(self) -> dict:
        return {"sim_time": self.sim, "epoch": "2027-01-15T00:00:00+03:30", "speed": 1.0}


class FakeGateway:
    def __init__(self):
        self.messages = []

    async def send_message(self, body: dict) -> SendResult:
        self.messages.append(dict(body))
        return SendResult(accepted=True, status=202, duplicate=False)


class FakeInventory:
    def __init__(self, items=None, mode: str = "ok"):
        self.items = list(items or [])
        self.dispatches = []
        self.mode = mode

    async def get_inventory(self) -> dict:
        return {"sim_time": 0.0, "items": [dict(it) for it in self.items]}

    async def dispatch(self, body: dict) -> DispatchResult:
        self.dispatches.append(dict(body))
        if self.mode == "ok":
            return DispatchResult(created=True, replay=False, error=None)
        if self.mode == "replay":
            return DispatchResult(created=False, replay=True, error=None)
        return DispatchResult(created=False, replay=False, error="conflict")


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store():
    s = Store()
    set_store(s)
    return s


@pytest.fixture
def settings():
    return Settings(_env_file=None)


@pytest.fixture
def kit():
    return build_kit()


@pytest.fixture
def clock():
    return FakeClock(100.0)


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
def inventory():
    return FakeInventory()


@pytest.fixture
def strategy():
    return TravelTimeRankingStrategy()


@pytest.fixture
def repos(store):
    return SimpleNamespace(
        request=RequestRepository(None),
        event=EventRepository(None),
        dispatch=DispatchRepository(None),
        notification=NotificationRepository(None),
        donor=DonorRepository(None),
        task=TaskRepository(None),
        hospital=HospitalRepository(None),
        center=CenterRepository(None),
    )


@pytest.fixture
def services(settings, kit, clock, gateway, inventory, strategy, repos):
    invitation = InvitationService(
        repos.request, repos.notification, repos.donor, repos.event, repos.hospital,
        gateway, clock, strategy, kit.travel_area_to_hospital, kit.compat, kit.rules,
        settings)
    callback = CallbackProcessor(repos.request, repos.event, repos.notification, gateway,
                                 invitation, settings)
    request_service = RequestService(repos.request, repos.event, repos.dispatch, repos.task,
                                     repos.hospital, kit.rules, settings)
    allocation = AllocationService(repos.request, repos.dispatch, inventory,
                                   kit.travel_center_to_hospital, kit.compat, settings)
    sla = SlaService(repos.request, invitation, settings)
    return SimpleNamespace(request=request_service, callback=callback, invitation=invitation,
                           allocation=allocation, sla=sla)


@pytest.fixture
def make_donor(store):
    def _make(donor_id="D00001", **overrides):
        defaults = dict(donor_id=donor_id, blood_group="O+", sex="M", age=30, weight_kg=70.0,
                        lat=0.0, lon=0.0, area_id="A000", quiet_start_hour=0,
                        quiet_end_hour=0, last_donation_at=None, last_donation_type=None,
                        permanently_excluded=0, notified_90d=0, defer_until=None,
                        defer_days=None)
        defaults.update(overrides)
        d = Donor(**defaults)
        store.donors[d.donor_id] = d
        return d

    return _make


@pytest.fixture
def make_request(store, kit):
    def _make(request_id="R-001", hospital_id="H01", blood_group="O+", product="red_cells",
              units=4, urgency="critical", status="open", sim=100.0, **overrides):
        defaults = dict(id=request_id, hospital_id=hospital_id, blood_group=blood_group,
                        product=product, units=units, urgency=urgency, note=None,
                        status=status, needed=units, confirmed=0, en_route=0, arrived=0,
                        fulfilled=0, stock_inflight=0, idempotency_key="ik-" + request_id,
                        idempotency_body_hash="hash", created_sim_min=sim,
                        updated_sim_min=sim,
                        sla_deadline_sim_min=sim + kit.rules["sla"][urgency],
                        wave_count=0, last_wave_sim_min=None)
        defaults.update(overrides)
        r = Request(**defaults)
        store.requests[r.id] = r
        return r

    return _make


@pytest.fixture
def add_hospital(store):
    def _make(hospital_id="H01", name="Demo Hospital"):
        h = Hospital(hospital_id=hospital_id, name=name, lat=0.0, lon=0.0,
                     request_weight=None, credit_level=None)
        store.hospitals[h.hospital_id] = h
        return h

    return _make
