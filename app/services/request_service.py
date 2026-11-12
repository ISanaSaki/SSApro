import json
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.data.models import Request, Task
from app.domain.state_machine import is_amendable, is_terminal

logger = logging.getLogger(__name__)


@dataclass
class CreateResult:
    created: bool
    replay: bool
    request_id: str
    status: str
    needed: int


@dataclass
class CreateError:
    code: str
    http_status: int
    message: str


class RequestService:
    def __init__(self, request_repo, event_repo, dispatch_repo, task_repo, hospital_repo, rules: dict,
                 settings: Settings):
        self._request_repo = request_repo
        self._event_repo = event_repo
        self._dispatch_repo = dispatch_repo
        self._task_repo = task_repo
        self._hospital_repo = hospital_repo
        self._rules = rules
        self._settings = settings

    async def create_request(self, payload: dict, idempotency_key: str, sim_min: float) -> CreateResult | CreateError:
        body_hash = json.dumps(payload, sort_keys=True)
        existing = await self._request_repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.idempotency_body_hash == body_hash:
                return self._replay(existing)
            return CreateError(code="idempotency_key_reuse", http_status=422,
                               message="same key, different body")
        if not await self._hospital_repo.exists(payload["hospital_id"]):
            return CreateError(code="unknown_hospital", http_status=400,
                               message="unregistered hospital_id")
        status = await self._initial_status(payload, sim_min)
        request_id = "R-" + uuid.uuid4().hex[:12]
        req = Request(
            id=request_id,
            hospital_id=payload["hospital_id"],
            blood_group=payload["blood_group"],
            product=payload["product"],
            units=payload["units"],
            urgency=payload["urgency"],
            note=payload.get("note"),
            status=status,
            needed=payload["units"],
            confirmed=0,
            en_route=0,
            arrived=0,
            fulfilled=0,
            stock_inflight=0,
            idempotency_key=idempotency_key,
            idempotency_body_hash=body_hash,
            created_sim_min=sim_min,
            updated_sim_min=sim_min,
            sla_deadline_sim_min=sim_min + float(self._rules["sla"][payload["urgency"]]),
            wave_count=0,
            last_wave_sim_min=None,
        )
        try:
            created = await self._request_repo.create(req)
        except IntegrityError:
            created = None
        if created is None:
            existing = await self._request_repo.get_by_idempotency_key(idempotency_key)
            if existing is not None and existing.idempotency_body_hash == body_hash:
                return self._replay(existing)
            return CreateError(code="idempotency_key_reuse", http_status=422,
                               message="same key, different body")
        if status == "open" and not self._settings.disable_outreach:
            await self._push_task("send_wave", request_id, sim_min)
        return CreateResult(created=True, replay=False, request_id=request_id, status=status,
                            needed=payload["units"])

    @staticmethod
    def _replay(req: Request) -> CreateResult:
        return CreateResult(created=False, replay=True, request_id=req.id, status=req.status,
                            needed=req.needed)

    async def _initial_status(self, payload: dict, sim_min: float) -> str:
        if self._settings.pending_policy != "burst_hold":
            return "open"
        if payload["units"] >= self._settings.suspicious_units_threshold:
            return "pending_review"
        recent = await self._request_repo.list(hospital_id=payload["hospital_id"])
        total = sum(r.units for r in recent
                    if r.status != "cancelled"
                    and r.created_sim_min >= sim_min - self._settings.burst_window_min)
        if total > self._settings.burst_max_units:
            return "pending_review"
        return "open"

    async def get_request_detail(self, request_id: str, sim_min: float) -> dict | None:
        r = await self._request_repo.get(request_id)
        if r is None:
            return None
        events = [dict(event_id=e.event_id, kind=e.kind, donor_id=e.donor_id,
                       notification_id=e.notification_id, response=e.response, event=e.event,
                       status=e.status, reason=e.reason, sim_time=e.sim_time)
                  for e in await self._event_repo.list_for_request(request_id)]
        dispatches = [dict(dispatch_id=d.dispatch_id, request_id=d.request_id, center_id=d.center_id,
                           blood_group=d.blood_group, product=d.product, units=d.units,
                           hospital_id=d.hospital_id, recipient_blood_group=d.recipient_blood_group,
                           created_sim_min=d.created_sim_min, delivery_sim_min=d.delivery_sim_min,
                           outcome=d.outcome)
                      for d in await self._dispatch_repo.list_for_request(request_id)]
        return dict(
            request_id=r.id, status=r.status, hospital_id=r.hospital_id, blood_group=r.blood_group,
            product=r.product, units=r.units, urgency=r.urgency, note=r.note,
            needed=r.needed, confirmed=r.confirmed, en_route=r.en_route, arrived=r.arrived,
            fulfilled=r.fulfilled, stock_inflight=r.stock_inflight,
            shortage=max(0, r.needed - r.fulfilled - r.stock_inflight),
            created_sim_min=r.created_sim_min, updated_sim_min=r.updated_sim_min,
            sla_deadline_sim_min=r.sla_deadline_sim_min, sim_min=sim_min, wave_count=r.wave_count,
            events=events, dispatches=dispatches,
        )

    async def amend_urgency(self, request_id: str, urgency: str, sim_min: float) -> dict | CreateError:
        r = await self._request_repo.get(request_id)
        if r is None:
            return CreateError(code="not_found", http_status=404, message=request_id)
        if not is_amendable(r.status):
            return CreateError(code="not_amendable", http_status=409, message=r.status)
        r.urgency = urgency
        r.sla_deadline_sim_min = sim_min + float(self._rules["sla"][urgency])
        r.updated_sim_min = sim_min
        await self._request_repo.update(r)
        if not self._settings.disable_outreach and r.needed - r.fulfilled - r.stock_inflight > 0:
            await self._push_task("send_wave", request_id, sim_min)
        return dict(request_id=request_id, urgency=urgency)

    async def cancel_request(self, request_id: str, sim_min: float) -> dict | CreateError:
        r = await self._request_repo.get(request_id)
        if r is None:
            return CreateError(code="not_found", http_status=404, message=request_id)
        if not is_terminal(r.status):
            r.status = "cancelled"
            r.updated_sim_min = sim_min
            await self._request_repo.update(r)
            await self._push_task("stop_outreach", request_id, sim_min, payload={"template": "cancelled"})
        return dict(request_id=request_id, status=r.status)

    async def approve_request(self, request_id: str, approved: bool, sim_min: float) -> dict | CreateError:
        r = await self._request_repo.get(request_id)
        if r is None:
            return CreateError(code="not_found", http_status=404, message=request_id)
        if r.status != "pending_review":
            return CreateError(code="not_approvable", http_status=409, message=r.status)
        if approved:
            r.status = "open"
        else:
            r.status = "cancelled"
        r.updated_sim_min = sim_min
        await self._request_repo.update(r)
        if approved and not self._settings.disable_outreach:
            await self._push_task("send_wave", request_id, sim_min)
        return dict(request_id=request_id, status=r.status)

    async def _push_task(self, task_type: str, request_id: str, sim_min: float,
                         payload: dict | None = None) -> None:
        await self._task_repo.push(Task(
            task_type=task_type,
            request_id=request_id,
            payload_json=json.dumps(payload or {}),
            status="pending",
            attempts=0,
            created_sim_min=sim_min,
            next_attempt_sim_min=sim_min,
        ))
