from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.api.schemas import DonorProgressCallback, DonorResponseCallback, GatewayStatusCallback

router = APIRouter()


@router.post("/callbacks/donor-response")
async def donor_response(body: DonorResponseCallback,
                         services: Services = Depends(get_services)):
    sim_min = await services.clock.now_sim()
    await services.callback_processor.process_donor_response(body.model_dump(), sim_min)
    return {"ok": True}


@router.post("/callbacks/donor-progress")
async def donor_progress(body: DonorProgressCallback,
                         services: Services = Depends(get_services)):
    sim_min = await services.clock.now_sim()
    await services.callback_processor.process_donor_progress(body.model_dump(), sim_min)
    return {"ok": True}


@router.post("/callbacks/gateway-status")
async def gateway_status(body: GatewayStatusCallback,
                         services: Services = Depends(get_services)):
    sim_min = await services.clock.now_sim()
    await services.callback_processor.process_gateway_status(body.model_dump(), sim_min)
    return {"ok": True}
