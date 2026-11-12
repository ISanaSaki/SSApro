from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.api.deps import Services, get_services, http_error, require_coordinator_token, \
    require_hospital_token
from app.api.schemas import AmendRequest, Approval, NewRequest
from app.services.request_service import CreateError

router = APIRouter()


@router.post("/requests")
async def create_request(
    payload: NewRequest,
    services: Services = Depends(get_services),
    _: None = Depends(require_hospital_token),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_sim_time: float | None = Header(default=None, alias="X-Sim-Time"),
):
    if not idempotency_key:
        raise http_error(400, "missing_idempotency_key", "Idempotency-Key required")
    if len(idempotency_key) > 128:
        raise http_error(400, "validation_error", "Idempotency-Key too long")
    sim_min = await services.clock.now_sim()
    result = await services.request_service.create_request(payload.model_dump(),
                                                           idempotency_key, sim_min)
    if isinstance(result, CreateError):
        raise http_error(result.http_status, result.code, result.message)
    body = {"request_id": result.request_id, "status": result.status, "needed": result.needed}
    return JSONResponse(status_code=200 if result.replay else 201, content=body)


@router.get("/requests/{request_id}")
async def get_request(request_id: str, services: Services = Depends(get_services),
                      _: None = Depends(require_hospital_token)):
    sim_min = await services.clock.now_sim()
    detail = await services.request_service.get_request_detail(request_id, sim_min)
    if detail is None:
        raise http_error(404, "not_found", request_id)
    return detail


@router.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: str, services: Services = Depends(get_services),
                         _: None = Depends(require_hospital_token)):
    sim_min = await services.clock.now_sim()
    result = await services.request_service.cancel_request(request_id, sim_min)
    if isinstance(result, CreateError):
        raise http_error(result.http_status, result.code, result.message)
    return result


@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str, body: Approval | None = None,
                          services: Services = Depends(get_services),
                          _: None = Depends(require_coordinator_token)):
    sim_min = await services.clock.now_sim()
    result = await services.request_service.approve_request(
        request_id, body.approved if body else True, sim_min)
    if isinstance(result, CreateError):
        raise http_error(result.http_status, result.code, result.message)
    return result


@router.post("/requests/{request_id}/amend")
async def amend_request(request_id: str, body: AmendRequest,
                        services: Services = Depends(get_services),
                        _: None = Depends(require_hospital_token)):
    sim_min = await services.clock.now_sim()
    result = await services.request_service.amend_urgency(request_id, body.urgency, sim_min)
    if isinstance(result, CreateError):
        raise http_error(result.http_status, result.code, result.message)
    return result
