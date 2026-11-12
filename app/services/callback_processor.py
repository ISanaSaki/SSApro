import logging
import uuid

from app.config import Settings
from app.data.models import Event, Notification
from app.domain.state_machine import InvalidTransitionError, is_terminal, transition

logger = logging.getLogger(__name__)


class CallbackProcessor:
    def __init__(self, request_repo, event_repo, notification_repo, gateway, invitation_service,
                 settings: Settings):
        self._request_repo = request_repo
        self._event_repo = event_repo
        self._notification_repo = notification_repo
        self._gateway = gateway
        self._invitation = invitation_service
        self._settings = settings

    async def process_donor_response(self, payload: dict, sim_min: float) -> bool:
        event = Event(
            event_id=payload["event_id"],
            request_id=payload.get("request_id") or "",
            donor_id=payload.get("donor_id"),
            notification_id=payload.get("notification_id"),
            kind="donor_response",
            response=payload["response"],
            event=None,
            status=None,
            reason=payload.get("reason"),
            sim_time=float(payload.get("sim_time", sim_min)),
            received_at_sim_min=sim_min,
        )
        if not await self._event_repo.add_or_ignore(event):
            return False
        r = await self._request_repo.get(event.request_id)
        if r is None:
            return True
        if payload["response"] == "accepted" and event.donor_id:
            count = await self._event_repo.count_for(event.request_id, "donor_response",
                                                     "response", "accepted", event.donor_id)
            if count == 1:
                r.confirmed += 1
                r.updated_sim_min = sim_min
                await self._request_repo.update(r)
                await self._send_confirmed(event)
        notification = await self._notification_repo.get(payload.get("notification_id"))
        if notification is not None:
            notification.response = payload["response"]
        return True

    async def _send_confirmed(self, event: Event) -> None:
        notification_id = "nt-" + uuid.uuid4().hex
        result = await self._gateway.send_message(dict(
            notification_id=notification_id, donor_id=event.donor_id, template="confirmed",
            request_id=event.request_id, callback_url=self._settings.self_url))
        if result.accepted or result.duplicate:
            await self._notification_repo.add(Notification(
                notification_id=notification_id, request_id=event.request_id,
                donor_id=event.donor_id, template="confirmed",
                created_sim_min=event.received_at_sim_min, sent_sim_min=event.received_at_sim_min,
                gateway_status=None, response=None))

    async def process_donor_progress(self, payload: dict, sim_min: float) -> bool:
        event = Event(
            event_id=payload["event_id"],
            request_id=payload.get("request_id") or "",
            donor_id=payload.get("donor_id"),
            notification_id=payload.get("notification_id"),
            kind="donor_progress",
            response=None,
            event=payload["event"],
            status=None,
            reason=payload.get("reason"),
            sim_time=float(payload.get("sim_time", sim_min)),
            received_at_sim_min=sim_min,
        )
        if not await self._event_repo.add_or_ignore(event):
            return False
        r = await self._request_repo.get(event.request_id)
        if r is None or event.donor_id is None:
            return True
        kind = payload["event"]
        if kind in ("en_route", "arrived"):
            count = await self._event_repo.count_for(event.request_id, "donor_progress",
                                                     "event", kind, event.donor_id)
            if count == 1:
                if kind == "en_route":
                    r.en_route += 1
                else:
                    r.arrived += 1
                r.updated_sim_min = sim_min
                await self._request_repo.update(r)
            return True
        if kind == "donated":
            count = await self._event_repo.count_for(event.request_id, "donor_progress",
                                                     "event", "donated", event.donor_id)
            if count == 1:
                was_zero = r.fulfilled == 0
                r.fulfilled += 1
                r.updated_sim_min = sim_min
                if not is_terminal(r.status):
                    if was_zero:
                        self._advance(r, "first_fulfilled")
                    if r.fulfilled >= r.needed and self._advance(r, "fully_fulfilled"):
                        await self._request_repo.update(r)
                        await self._invitation.stop_outreach(event.request_id, "not_needed")
                        return True
                await self._request_repo.update(r)
        return True

    @staticmethod
    def _advance(r, event: str) -> bool:
        try:
            r.status = transition(r.status, event)
            return True
        except InvalidTransitionError:
            return False

    async def process_gateway_status(self, payload: dict, sim_min: float) -> bool:
        event = Event(
            event_id=payload["event_id"],
            request_id=payload.get("request_id") or "",
            donor_id=payload.get("donor_id"),
            notification_id=payload.get("notification_id"),
            kind="gateway_status",
            response=None,
            event=None,
            status=payload["status"],
            reason=None,
            sim_time=float(payload.get("sim_time", sim_min)),
            received_at_sim_min=sim_min,
        )
        return await self._event_repo.add_or_ignore(event)
