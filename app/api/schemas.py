from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BLOOD_GROUPS = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
PRODUCTS = ["red_cells", "platelets", "plasma"]
URGENCIES = ["critical", "urgent", "planned"]
PROGRESS_EVENTS = ["en_route", "arrived", "screen_pass", "screen_fail", "donated", "no_show"]
GATEWAY_STATUSES = ["queued", "sent", "delivered", "failed", "expired"]


class NewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hospital_id: str
    blood_group: Literal["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
    product: Literal["red_cells", "platelets", "plasma"]
    units: int = Field(ge=1, le=20)
    urgency: Literal["critical", "urgent", "planned"]
    note: str | None = Field(default=None, max_length=500)


class AmendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urgency: Literal["critical", "urgent", "planned"]


class Approval(BaseModel):
    approved: bool = True
    note: str | None = None


class DonorResponseCallback(BaseModel):
    event_id: str
    request_id: str
    donor_id: str
    notification_id: str
    response: Literal["accepted", "declined"]
    reason: str | None = None
    sim_time: float


class DonorProgressCallback(BaseModel):
    event_id: str
    request_id: str
    donor_id: str
    notification_id: str | None = None
    event: Literal["en_route", "arrived", "screen_pass", "screen_fail", "donated", "no_show"]
    reason: str | None = None
    sim_time: float


class GatewayStatusCallback(BaseModel):
    event_id: str
    notification_id: str
    request_id: str
    donor_id: str
    status: Literal["queued", "sent", "delivered", "failed", "expired"]
    sim_time: float


class DonorRespond(BaseModel):
    donor_id: str
    request_id: str
    response: Literal["accepted", "declined"]


class DonorProgress(BaseModel):
    donor_id: str
    request_id: str
    event: Literal["en_route", "arrived", "screen_pass", "screen_fail", "donated", "no_show"]
