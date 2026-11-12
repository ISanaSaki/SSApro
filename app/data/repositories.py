from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.loader import EPOCH, sim_minutes_to_iso
from app.data.models import (
    Center,
    Dispatch,
    Donor,
    DonorHistory,
    Event,
    Hospital,
    Notification,
    Request,
    Task,
)

_EVENT_FIELD_COLUMNS = {
    "response": Event.response,
    "event": Event.event,
    "status": Event.status,
}


def _row_values(obj) -> dict:
    # Unset columns stay out of the INSERT so SQLAlchemy applies Python-side defaults.
    return {key: value for key, value in vars(obj).items() if not key.startswith("_")}


async def _insert_or_ignore(session: AsyncSession, model, obj, conflict_column: str) -> bool:
    stmt = (
        sqlite_insert(model.__table__)
        .values(_row_values(obj))
        .on_conflict_do_nothing(index_elements=[conflict_column])
    )
    result = await session.execute(stmt)
    return result.rowcount == 1


class RequestRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, req: Request) -> Request | None:
        """Insert a request; returns None on idempotency_key conflict so the service re-reads.

        The rollback is deliberate: a failed flush poisons the transaction until rolled back.
        """
        self._session.add(req)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            return None
        return req

    async def get(self, request_id: str) -> Request | None:
        return await self._session.get(Request, request_id)

    async def get_by_idempotency_key(self, key: str) -> Request | None:
        stmt = select(Request).where(Request.idempotency_key == key)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list(self, hospital_id: str | None = None, status: str | None = None) -> list[Request]:
        stmt = select(Request)
        if hospital_id is not None:
            stmt = stmt.where(Request.hospital_id == hospital_id)
        if status is not None:
            stmt = stmt.where(Request.status == status)
        stmt = stmt.order_by(Request.created_sim_min.desc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def update(self, req: Request) -> None:
        await self._session.merge(req)
        await self._session.flush()


class EventRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_or_ignore(self, ev: Event) -> bool:
        """Insert an event; returns False when event_id already exists (duplicate)."""
        return await _insert_or_ignore(self._session, Event, ev, "event_id")

    async def exists(self, event_id: str) -> bool:
        stmt = select(Event.event_id).where(Event.event_id == event_id).limit(1)
        return (await self._session.execute(stmt)).first() is not None

    async def count_for(self, request_id: str, kind: str, field: str, value: str, donor_id: str) -> int:
        column = _EVENT_FIELD_COLUMNS.get(field)
        if column is None:
            raise ValueError(f"unsupported event field: {field!r}")
        stmt = (
            select(func.count())
            .select_from(Event)
            .where(
                Event.request_id == request_id,
                Event.kind == kind,
                column == value,
                Event.donor_id == donor_id,
            )
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def list_for_request(self, request_id: str) -> list[Event]:
        stmt = (
            select(Event)
            .where(Event.request_id == request_id)
            .order_by(Event.received_at_sim_min.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())


class DispatchRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_or_ignore(self, dispatch: Dispatch) -> bool:
        """Insert a dispatch; returns False when dispatch_id already exists (replay)."""
        return await _insert_or_ignore(self._session, Dispatch, dispatch, "dispatch_id")

    async def list_for_request(self, request_id: str) -> list[Dispatch]:
        stmt = (
            select(Dispatch)
            .where(Dispatch.request_id == request_id)
            .order_by(Dispatch.created_sim_min.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def due_deliveries(self, sim_min: float) -> list[Dispatch]:
        stmt = select(Dispatch).where(
            Dispatch.outcome == "created",
            Dispatch.delivery_sim_min <= sim_min,
        )
        return list((await self._session.execute(stmt)).scalars().all())


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, notification: Notification) -> None:
        self._session.add(notification)
        await self._session.flush()

    async def get(self, notification_id: str) -> Notification | None:
        return await self._session.get(Notification, notification_id)

    async def find(self, request_id: str, donor_id: str) -> Notification | None:
        stmt = select(Notification).where(
            Notification.request_id == request_id,
            Notification.donor_id == donor_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_request(self, request_id: str) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.request_id == request_id)
            .order_by(Notification.created_sim_min.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def accepted_not_donated(self, request_id: str) -> list[Notification]:
        donated_exists = (
            select(Event.event_id)
            .where(
                Event.request_id == Notification.request_id,
                Event.donor_id == Notification.donor_id,
                Event.event == "donated",
            )
            .exists()
        )
        stmt = select(Notification).where(
            Notification.request_id == request_id,
            Notification.response == "accepted",
            ~donated_exists,
        )
        return list((await self._session.execute(stmt)).scalars().all())


class DonorRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, donor_id: str) -> Donor | None:
        return await self._session.get(Donor, donor_id)

    async def eligible(
        self,
        product: str,
        recipient_group: str,
        request_id: str,
        sim_min: float,
        rules: dict,
        compat: dict,
    ) -> list[Donor]:
        """All seven eligibility filters from the frozen contract, applied in one SQL query."""
        donor_groups = compat.get(product, {}).get(recipient_group) or []
        if not donor_groups:
            return []

        now_iso = sim_minutes_to_iso(EPOCH, sim_min)
        local_hour = (int(sim_min) // 60) % 24
        age_min = rules.get("age_min", 18)
        age_max = rules.get("age_max", 65)
        weight_min = rules.get("weight_min_kg", 50)
        interval_wb_male = rules.get("interval_wb_male", 60)
        interval_wb_female = rules.get("interval_wb_female", 90)
        interval_apheresis = rules.get("interval_apheresis", 14)
        cross_block = rules.get("cross_block", 14)

        same_type_gap = case(
            (
                product == "red_cells",
                case((Donor.sex == "M", interval_wb_male), else_=interval_wb_female),
            ),
            else_=interval_apheresis,
        )
        required_gap_days = case(
            (Donor.last_donation_type.is_(None), 0),
            (Donor.last_donation_type != product, cross_block),
            else_=same_type_gap,
        )
        gap_ok = or_(
            Donor.last_donation_at.is_(None),
            (func.julianday(now_iso) - func.julianday(Donor.last_donation_at))
            >= required_gap_days,
        )

        quiet_start = Donor.quiet_start_hour
        quiet_end = Donor.quiet_end_hour
        quiet_ok = or_(
            quiet_start == quiet_end,
            and_(quiet_start < quiet_end, or_(local_hour < quiet_start, local_hour >= quiet_end)),
            and_(quiet_start > quiet_end, and_(local_hour >= quiet_end, local_hour < quiet_start)),
        )

        already_invited = (
            select(Notification.notification_id)
            .where(
                Notification.request_id == request_id,
                Notification.donor_id == Donor.donor_id,
            )
            .exists()
        )

        stmt = (
            select(Donor)
            .where(
                Donor.permanently_excluded == 0,
                Donor.age >= age_min,
                Donor.age <= age_max,
                Donor.weight_kg >= weight_min,
                Donor.blood_group.in_(donor_groups),
                or_(Donor.defer_until.is_(None), Donor.defer_until < now_iso),
                gap_ok,
                quiet_ok,
                ~already_invited,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def history_features(self, donor_id: str) -> dict:
        mean_delay = func.avg(
            case((DonorHistory.responded == 1, DonorHistory.response_delay_min), else_=None)
        )
        stmt = select(
            func.count(DonorHistory.id),
            func.coalesce(func.sum(DonorHistory.responded), 0),
            func.coalesce(func.sum(DonorHistory.accepted), 0),
            func.coalesce(func.sum(DonorHistory.donated), 0),
            mean_delay,
        ).where(DonorHistory.donor_id == donor_id)
        notified, responded, accepted, donated, mean = (await self._session.execute(stmt)).one()
        notified = int(notified or 0)
        responded = int(responded or 0)
        accepted = int(accepted or 0)
        donated = int(donated or 0)
        return {
            "notified_count": notified,
            "responded_count": responded,
            "accepted_count": accepted,
            "donated_count": donated,
            "response_rate": responded / notified if notified else 0.0,
            "accept_rate": accepted / notified if notified else 0.0,
            "donate_rate": donated / notified if notified else 0.0,
            "mean_response_delay_min": float(mean) if mean is not None else None,
        }


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def push(self, task: Task) -> None:
        self._session.add(task)
        await self._session.flush()

    async def pop_due(self, sim_min: float, limit: int) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.status == "pending", Task.next_attempt_sim_min <= sim_min)
            .order_by(Task.id.asc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def finish(self, task_id: int, ok: bool) -> None:
        task = await self._session.get(Task, task_id)
        if task is None:
            return
        task.status = "done" if ok else "failed"
        await self._session.flush()


class HospitalRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists(self, hospital_id: str) -> bool:
        return await self._session.get(Hospital, hospital_id) is not None

    async def list(self) -> list[Hospital]:
        stmt = select(Hospital).order_by(Hospital.hospital_id.asc())
        return list((await self._session.execute(stmt)).scalars().all())


class CenterRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list(self) -> list[Center]:
        stmt = select(Center).order_by(Center.center_id.asc())
        return list((await self._session.execute(stmt)).scalars().all())
