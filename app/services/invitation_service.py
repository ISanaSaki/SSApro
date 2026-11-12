import logging
import uuid
from datetime import datetime

from app.config import Settings
from app.data.models import Notification
from app.domain.ranking import RankingContext
from app.domain.state_machine import is_terminal, transition

logger = logging.getLogger(__name__)

EPOCH = datetime(2027, 1, 15, 0, 0)


def local_hour(sim_min: float) -> int:
    return int(sim_min // 60) % 24


def in_quiet_hours(donor, sim_min: float) -> bool:
    start, end = donor.quiet_start_hour, donor.quiet_end_hour
    if start == end:
        return False
    hour = local_hour(sim_min)
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def defer_sim_min(defer_until: str | None) -> float | None:
    if not defer_until:
        return None
    try:
        return (datetime.fromisoformat(defer_until) - EPOCH).total_seconds() / 60.0
    except ValueError:
        return None


def donation_interval_ok(donor, product: str, sim_min: float, rules: dict) -> bool:
    if not donor.last_donation_at:
        return True
    try:
        last = datetime.fromisoformat(donor.last_donation_at)
    except ValueError:
        return True
    since_days = sim_min / 1440.0 - (last - EPOCH).total_seconds() / 86400.0
    prev_type = donor.last_donation_type
    if product == "red_cells":
        same = prev_type == "whole_blood"
        need = rules["interval_wb_male"] if donor.sex == "M" else rules["interval_wb_female"]
    else:
        same = prev_type == product
        need = rules["interval_apheresis"]
    if not same:
        need = rules["cross_block"]
    return since_days >= need


class InvitationService:
    def __init__(self, request_repo, notification_repo, donor_repo, event_repo, hospital_repo,
                 gateway, clock, strategy, travel_area_to_hospital: dict, compat: dict, rules: dict,
                 settings: Settings):
        self._request_repo = request_repo
        self._notification_repo = notification_repo
        self._donor_repo = donor_repo
        self._event_repo = event_repo
        self._hospital_repo = hospital_repo
        self._gateway = gateway
        self._clock = clock
        self._strategy = strategy
        self._travel = travel_area_to_hospital
        self._compat = compat
        self._rules = rules
        self._settings = settings

    def recheck(self, donor, product: str, recipient_group: str, sim_min: float) -> bool:
        """Defense-in-depth re-verification of every eligibility filter (safety gate)."""
        if int(donor.permanently_excluded or 0) != 0:
            return False
        if not (self._rules["age_min"] <= int(donor.age) <= self._rules["age_max"]):
            return False
        if float(donor.weight_kg) < self._rules["weight_min_kg"]:
            return False
        defer_at = defer_sim_min(donor.defer_until)
        if defer_at is not None and sim_min < defer_at:
            return False
        if not donation_interval_ok(donor, product, sim_min, self._rules):
            return False
        if in_quiet_hours(donor, sim_min):
            return False
        if donor.blood_group not in self._compat.get(product, {}).get(recipient_group, []):
            return False
        return True

    async def build_wave(self, request_id: str, sim_min: float) -> int:
        if self._settings.disable_outreach:
            return 0
        r = await self._request_repo.get(request_id)
        if r is None or is_terminal(r.status):
            return 0
        shortage = r.needed - r.fulfilled - r.stock_inflight
        if shortage <= 0:
            return 0
        candidates = await self._donor_repo.eligible(r.product, r.blood_group, request_id, sim_min,
                                                     self._rules, self._compat)
        candidates = [d for d in candidates if self.recheck(d, r.product, r.blood_group, sim_min)]
        travel = {}
        for d in candidates:
            minutes = self._travel.get((d.area_id, r.hospital_id))
            if minutes is None:
                continue
            travel[d.donor_id] = minutes
        candidates = [d for d in candidates if d.donor_id in travel]
        hospitals = await self._hospital_repo.list()
        hospital = next((h for h in hospitals if h.hospital_id == r.hospital_id), None)
        context = RankingContext(request=r, hospital=hospital, sim_min=sim_min, travel_minutes=travel)
        ranked = self._strategy.rank(candidates, context)
        cap = min(max(shortage * self._settings.wave_size_factor, self._settings.wave_min_size),
                  self._settings.wave_max_size)
        sent = 0
        for entry in ranked[:cap]:
            if await self._notification_repo.find(request_id, entry.donor_id) is not None:
                continue
            notification_id = "nt-" + uuid.uuid4().hex
            result = await self._gateway.send_message(dict(
                notification_id=notification_id, donor_id=entry.donor_id,
                template="request_wave", request_id=request_id,
                callback_url=self._settings.self_url))
            if result.accepted or result.duplicate:
                await self._notification_repo.add(Notification(
                    notification_id=notification_id, request_id=request_id,
                    donor_id=entry.donor_id, template="request_wave",
                    created_sim_min=sim_min, sent_sim_min=sim_min,
                    gateway_status=None, response=None))
                sent += 1
        r.wave_count += 1
        r.last_wave_sim_min = sim_min
        r.updated_sim_min = sim_min
        if sent > 0 and r.status == "open":
            r.status = transition(r.status, "wave_started")
        await self._request_repo.update(r)
        return sent

    async def stop_outreach(self, request_id: str, template: str) -> int:
        sent = 0
        sim_min = await self._clock.now_sim()
        for n in await self._notification_repo.accepted_not_donated(request_id):
            notification_id = "nt-" + uuid.uuid4().hex
            result = await self._gateway.send_message(dict(
                notification_id=notification_id, donor_id=n.donor_id, template=template,
                request_id=request_id, callback_url=self._settings.self_url))
            if result.accepted or result.duplicate:
                await self._notification_repo.add(Notification(
                    notification_id=notification_id, request_id=request_id,
                    donor_id=n.donor_id, template=template,
                    created_sim_min=sim_min, sent_sim_min=sim_min,
                    gateway_status=None, response=None))
                sent += 1
        return sent

    async def send_reminders(self, request_id: str, sim_min: float) -> int:
        sent = 0
        for n in await self._notification_repo.accepted_not_donated(request_id):
            arrived = await self._event_repo.count_for(request_id, "donor_progress", "event",
                                                       "arrived", n.donor_id)
            if arrived > 0:
                continue
            notification_id = "nt-" + uuid.uuid4().hex
            result = await self._gateway.send_message(dict(
                notification_id=notification_id, donor_id=n.donor_id, template="reminder",
                request_id=request_id, callback_url=self._settings.self_url))
            if result.accepted or result.duplicate:
                await self._notification_repo.add(Notification(
                    notification_id=notification_id, request_id=request_id,
                    donor_id=n.donor_id, template="reminder",
                    created_sim_min=sim_min, sent_sim_min=sim_min,
                    gateway_status=None, response=None))
                sent += 1
        return sent
