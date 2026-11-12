import logging
import uuid

from app.config import Settings
from app.data.models import Dispatch
from app.domain.state_machine import is_terminal

logger = logging.getLogger(__name__)


class AllocationService:
    def __init__(self, request_repo, dispatch_repo, inventory_client, travel_center_to_hospital: dict,
                 compat: dict, settings: Settings):
        self._request_repo = request_repo
        self._dispatch_repo = dispatch_repo
        self._inventory = inventory_client
        self._travel = travel_center_to_hospital
        self._compat = compat
        self._settings = settings

    async def allocate(self, request_id: str, sim_min: float) -> dict:
        r = await self._request_repo.get(request_id)
        if r is None or is_terminal(r.status):
            return {"dispatched_units": 0, "shortage": 0}
        need = r.needed - r.fulfilled - r.stock_inflight
        if need <= 0:
            return {"dispatched_units": 0, "shortage": 0}
        snapshot = await self._inventory.get_inventory()
        allowed = self._compat.get(r.product, {}).get(r.blood_group, [])
        usable = [it for it in snapshot.get("items", [])
                  if it.get("product") == r.product
                  and it.get("blood_group") in allowed
                  and it.get("expires_sim_min", 0) > sim_min]
        usable.sort(key=lambda it: it.get("expires_sim_min", float("inf")))
        picks: dict[tuple, int] = {}
        for it in usable:
            remaining = need - sum(picks.values())
            if remaining <= 0:
                break
            take = min(int(it.get("units", 0)), remaining)
            if take > 0:
                key = (it["center_id"], it["blood_group"])
                picks[key] = picks.get(key, 0) + take
        dispatched = 0
        for (center_id, group), units in picks.items():
            dispatch_id = "dsp-" + uuid.uuid4().hex
            result = await self._inventory.dispatch(dict(
                dispatch_id=dispatch_id, request_id=request_id, center_id=center_id,
                blood_group=group, product=r.product, units=units,
                hospital_id=r.hospital_id, recipient_blood_group=r.blood_group))
            travel = self._travel.get((center_id, r.hospital_id), 0.0)
            delivery_sim_min = sim_min + 10.0 + travel
            dispatch = Dispatch(
                dispatch_id=dispatch_id, request_id=request_id, center_id=center_id,
                blood_group=group, product=r.product, units=units,
                hospital_id=r.hospital_id, recipient_blood_group=r.blood_group,
                created_sim_min=sim_min, delivery_sim_min=delivery_sim_min,
                outcome="created" if (result.created or result.replay) else "failed")
            if result.created or result.replay:
                if await self._dispatch_repo.add_or_ignore(dispatch):
                    r.stock_inflight += units
                    dispatched += units
            else:
                await self._dispatch_repo.add_or_ignore(dispatch)
        r.updated_sim_min = sim_min
        await self._request_repo.update(r)
        shortage = max(0, r.needed - r.fulfilled - r.stock_inflight)
        return {"dispatched_units": dispatched, "shortage": shortage}
