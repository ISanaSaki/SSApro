from sqlalchemy import Float, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    hospital_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    blood_group: Mapped[str] = mapped_column(Text, nullable=False)
    product: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    urgency: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    needed: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    en_route: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arrived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fulfilled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stock_inflight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    idempotency_body_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    updated_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    sla_deadline_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    wave_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_wave_sim_min: Mapped[float | None] = mapped_column(Float, nullable=True)


class Dispatch(Base):
    __tablename__ = "dispatches"

    dispatch_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    center_id: Mapped[str] = mapped_column(Text, nullable=False)
    blood_group: Mapped[str] = mapped_column(Text, nullable=False)
    product: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    hospital_id: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_blood_group: Mapped[str] = mapped_column(Text, nullable=False)
    created_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    delivery_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False, default="created")


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    donor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    event: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sim_time: Mapped[float] = mapped_column(Float, nullable=False)
    received_at_sim_min: Mapped[float] = mapped_column(Float, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_request_id_donor_id", "request_id", "donor_id"),
    )

    notification_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    donor_id: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    created_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    sent_sim_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    gateway_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)


class Donor(Base):
    __tablename__ = "donors"

    donor_id: Mapped[str] = mapped_column(Text, primary_key=True)
    blood_group: Mapped[str] = mapped_column(Text, nullable=False)
    sex: Mapped[str] = mapped_column(Text, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    area_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    quiet_start_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    quiet_end_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    last_donation_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_donation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    permanently_excluded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notified_90d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    defer_until: Mapped[str | None] = mapped_column(Text, nullable=True)
    defer_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Hospital(Base):
    __tablename__ = "hospitals"

    hospital_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    request_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    credit_level: Mapped[str | None] = mapped_column(Text, nullable=True)


class Center(Base):
    __tablename__ = "centers"

    center_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    beds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    close_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DonorHistory(Base):
    __tablename__ = "donor_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    donor_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    notified_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    wave: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_delay_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrived: Mapped[int | None] = mapped_column(Integer, nullable=True)
    donated: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
    next_attempt_sim_min: Mapped[float] = mapped_column(Float, nullable=False)
