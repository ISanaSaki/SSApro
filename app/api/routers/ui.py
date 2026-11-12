import uuid

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services, http_error, require_any_token, \
    require_coordinator_token, require_hospital_token
from app.api.schemas import DonorProgress, DonorRespond

router = APIRouter()


async def _donor_invitations(services: Services, donor_id: str, requests: list) -> list:
    invitations = []
    for r in requests:
        notifications = [
            n for n in await services.notification_repo.list_for_request(r.id)
            if n.donor_id == donor_id
        ]
        if not notifications:
            continue
        events = await services.event_repo.list_for_request(r.id)
        for n in notifications:
            statuses = [e.status for e in events
                        if e.notification_id == n.notification_id and e.kind == "gateway_status"]
            responses = [e.response for e in events
                         if e.request_id == r.id and e.donor_id == donor_id
                         and e.kind == "donor_response"]
            progress = [e.event for e in events
                        if e.request_id == r.id and e.donor_id == donor_id
                        and e.kind == "donor_progress"]
            invitations.append(dict(
                notification_id=n.notification_id, request_id=n.request_id, template=n.template,
                created_sim_min=n.created_sim_min,
                gateway_status=statuses[-1] if statuses else None,
                response=responses[-1] if responses else None,
                event=progress[-1] if progress else None,
            ))
    return invitations


@router.get("/api/requests")
async def list_requests(hospital_id: str | None = None, status: str | None = None,
                        services: Services = Depends(get_services),
                        _: None = Depends(require_any_token)):
    sim_min = await services.clock.now_sim()
    requests = await services.request_repo.list(hospital_id=hospital_id, status=status)
    details = []
    for r in requests:
        detail = await services.request_service.get_request_detail(r.id, sim_min)
        if detail is not None:
            details.append(detail)
    return {"requests": details}


@router.get("/api/requests/{request_id}")
async def get_request_detail(request_id: str, services: Services = Depends(get_services),
                             _: None = Depends(require_any_token)):
    sim_min = await services.clock.now_sim()
    detail = await services.request_service.get_request_detail(request_id, sim_min)
    if detail is None:
        raise http_error(404, "not_found", request_id)
    return detail


@router.get("/api/inventory")
async def get_inventory(services: Services = Depends(get_services),
                        _: None = Depends(require_coordinator_token)):
    return await services.inventory.get_inventory()


@router.get("/api/hospitals")
async def list_hospitals(services: Services = Depends(get_services),
                         _: None = Depends(require_hospital_token)):
    hospitals = await services.hospital_repo.list()
    return {"hospitals": [{"hospital_id": h.hospital_id, "name": h.name} for h in hospitals]}


@router.get("/api/centers")
async def list_centers(services: Services = Depends(get_services),
                       _: None = Depends(require_coordinator_token)):
    centers = await services.center_repo.list()
    return {"centers": [{"center_id": c.center_id, "name": c.name} for c in centers]}


@router.get("/api/clock")
async def get_clock(services: Services = Depends(get_services)):
    return await services.clock.payload()


@router.get("/api/donor/invitations")
async def donor_invitations(donor_id: str, services: Services = Depends(get_services)):
    requests = await services.request_repo.list()
    invitations = await _donor_invitations(services, donor_id, requests)
    return {"donor_id": donor_id, "invitations": invitations}


@router.post("/api/donor/respond")
async def donor_respond(body: DonorRespond, services: Services = Depends(get_services)):
    sim_min = await services.clock.now_sim()
    payload = dict(
        event_id="ui-" + uuid.uuid4().hex,
        request_id=body.request_id,
        donor_id=body.donor_id,
        notification_id="",
        response=body.response,
        reason=None,
        sim_time=sim_min,
    )
    await services.callback_processor.process_donor_response(payload, sim_min)
    return {"ok": True}


@router.post("/api/donor/progress")
async def donor_progress(body: DonorProgress, services: Services = Depends(get_services)):
    sim_min = await services.clock.now_sim()
    payload = dict(
        event_id="ui-" + uuid.uuid4().hex,
        request_id=body.request_id,
        donor_id=body.donor_id,
        notification_id=None,
        event=body.event,
        reason=None,
        sim_time=sim_min,
    )
    await services.callback_processor.process_donor_progress(payload, sim_min)
    return {"ok": True}
