import logging

from app.domain.state_machine import is_terminal, transition

logger = logging.getLogger(__name__)


class SlaService:
    def __init__(self, request_repo, invitation_service, settings):
        self._request_repo = request_repo
        self._invitation = invitation_service
        self._settings = settings

    async def check_expired(self, sim_min: float) -> list:
        expired = []
        for r in await self._request_repo.list():
            if is_terminal(r.status) or r.status == "pending_review":
                continue
            if r.sla_deadline_sim_min <= sim_min:
                r.status = transition(r.status, "expired")
                r.updated_sim_min = sim_min
                await self._request_repo.update(r)
                await self._invitation.stop_outreach(r.id, "cancelled")
                expired.append(r.id)
        return expired
