import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request
from fastapi.params import Depends

from app.config import Settings, load_settings
from app.data.repositories import (CenterRepository, DispatchRepository, DonorRepository,
                                   EventRepository, HospitalRepository, NotificationRepository,
                                   RequestRepository, TaskRepository)
from app.services.allocation_service import AllocationService
from app.services.callback_processor import CallbackProcessor
from app.services.invitation_service import InvitationService
from app.services.request_service import RequestService
from app.services.sla_service import SlaService


def http_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:]


def _guard(authorization: str | None, expected: str, who: str) -> None:
    token = _bearer(authorization)
    if token is None or not secrets.compare_digest(token, expected):
        raise http_error(401, "unauthorized", f"{who} token")


def require_hospital_token(authorization: str | None = Header(default=None, alias="Authorization"),
                           settings: Settings = Depends(load_settings)) -> None:
    _guard(authorization, settings.hospital_token, "hospital")


def require_coordinator_token(authorization: str | None = Header(default=None, alias="Authorization"),
                              settings: Settings = Depends(load_settings)) -> None:
    _guard(authorization, settings.coordinator_token, "coordinator")


def require_any_token(authorization: str | None = Header(default=None, alias="Authorization"),
                      settings: Settings = Depends(load_settings)) -> None:
    token = _bearer(authorization)
    if token is None or not (secrets.compare_digest(token, settings.hospital_token)
                             or secrets.compare_digest(token, settings.coordinator_token)):
        raise http_error(401, "unauthorized", "hospital or coordinator token")


@dataclass
class Services:
    request_service: RequestService
    allocation_service: AllocationService
    invitation_service: InvitationService
    callback_processor: CallbackProcessor
    sla_service: SlaService
    clock: object
    inventory: object
    request_repo: RequestRepository
    event_repo: EventRepository
    dispatch_repo: DispatchRepository
    notification_repo: NotificationRepository
    task_repo: TaskRepository
    hospital_repo: HospitalRepository
    center_repo: CenterRepository
    settings: Settings


def build_services(session, state) -> Services:
    settings: Settings = state.settings
    kit = state.kit_data
    request_repo = RequestRepository(session)
    event_repo = EventRepository(session)
    dispatch_repo = DispatchRepository(session)
    notification_repo = NotificationRepository(session)
    donor_repo = DonorRepository(session)
    task_repo = TaskRepository(session)
    hospital_repo = HospitalRepository(session)
    center_repo = CenterRepository(session)
    invitation = InvitationService(
        request_repo, notification_repo, donor_repo, event_repo, hospital_repo,
        state.gateway, state.clock, state.ranking_strategy,
        kit.travel_area_to_hospital, kit.compat, kit.rules, settings)
    callback = CallbackProcessor(request_repo, event_repo, notification_repo, state.gateway,
                                 invitation, settings)
    request_service = RequestService(request_repo, event_repo, dispatch_repo, task_repo,
                                     hospital_repo, kit.rules, settings)
    allocation = AllocationService(request_repo, dispatch_repo, state.inventory,
                                   kit.travel_center_to_hospital, kit.compat, settings)
    sla = SlaService(request_repo, invitation, settings)
    return Services(
        request_service=request_service,
        allocation_service=allocation,
        invitation_service=invitation,
        callback_processor=callback,
        sla_service=sla,
        clock=state.clock,
        inventory=state.inventory,
        request_repo=request_repo,
        event_repo=event_repo,
        dispatch_repo=dispatch_repo,
        notification_repo=notification_repo,
        task_repo=task_repo,
        hospital_repo=hospital_repo,
        center_repo=center_repo,
        settings=settings,
    )


async def get_services(request: Request):
    async with request.app.state.sessionmaker() as session:
        yield build_services(session, request.app.state)
