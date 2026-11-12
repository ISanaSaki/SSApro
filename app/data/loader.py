import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import yaml
from sqlalchemy import bindparam, delete, insert, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.data.models import Center, Donor, DonorHistory, Hospital

EPOCH = datetime(2027, 1, 15, tzinfo=timezone(timedelta(hours=3, minutes=30)))
BULK_CHUNK = 20_000


@dataclass
class KitData:
    compat: dict
    rules: dict
    travel_area_to_hospital: dict
    travel_center_to_hospital: dict
    travel_area_to_center: dict
    epoch: datetime = EPOCH


def sim_minutes_to_iso(epoch: datetime, sim_min: float) -> str:
    """Convert simulation minutes to the local naive ISO format used by kit CSVs."""
    return (epoch + timedelta(minutes=sim_min)).strftime("%Y-%m-%dT%H:%M:%S")


def _opt_text(value: str) -> str | None:
    return value.strip() or None


def _opt_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def _opt_float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _req_int(value: str) -> int:
    return int(value.strip())


def _req_float(value: str) -> float:
    return float(value.strip())


def _donor_row(raw: dict) -> dict:
    return {
        "donor_id": raw["donor_id"].strip(),
        "blood_group": raw["blood_group"].strip(),
        "sex": raw["sex"].strip(),
        "age": _req_int(raw["age"]),
        "weight_kg": _req_float(raw["weight_kg"]),
        "lat": _req_float(raw["lat"]),
        "lon": _req_float(raw["lon"]),
        "area_id": raw["area_id"].strip(),
        "quiet_start_hour": _req_int(raw["quiet_start_hour"]),
        "quiet_end_hour": _req_int(raw["quiet_end_hour"]),
        "last_donation_at": _opt_text(raw["last_donation_at"]),
        "last_donation_type": _opt_text(raw["last_donation_type"]),
        "permanently_excluded": _req_int(raw["permanently_excluded"]),
        "notified_90d": _req_int(raw["notified_90d"]),
    }


def _hospital_row(raw: dict) -> dict:
    return {
        "hospital_id": raw["hospital_id"].strip(),
        "name": raw["name"].strip(),
        "lat": _req_float(raw["lat"]),
        "lon": _req_float(raw["lon"]),
        "request_weight": _opt_float(raw["request_weight"]),
        "credit_level": _opt_text(raw["credit_level"]),
    }


def _center_row(raw: dict) -> dict:
    return {
        "center_id": raw["center_id"].strip(),
        "name": raw["name"].strip(),
        "lat": _req_float(raw["lat"]),
        "lon": _req_float(raw["lon"]),
        "beds": _opt_int(raw["beds"]),
        "open_hour": _opt_int(raw["open_hour"]),
        "close_hour": _opt_int(raw["close_hour"]),
    }


def _history_row(raw: dict) -> dict:
    return {
        "request_id": raw["request_id"].strip(),
        "donor_id": raw["donor_id"].strip(),
        "notified_at": _opt_text(raw["notified_at"]),
        "wave": _opt_int(raw["wave"]),
        "responded": _opt_int(raw["responded"]),
        "accepted": _opt_int(raw["accepted"]),
        "response_delay_min": _opt_float(raw["response_delay_min"]),
        "arrived": _opt_int(raw["arrived"]),
        "donated": _opt_int(raw["donated"]),
    }


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"missing kit file: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _read_travel_matrix(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"missing kit file: {path}")
    matrix: dict[tuple[str, str], float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        origin_col = reader.fieldnames[0]
        destination_cols = reader.fieldnames[1:]
        for row in reader:
            origin = row[origin_col].strip()
            for destination in destination_cols:
                value = row[destination].strip()
                if value:
                    matrix[(origin, destination)] = float(value)
    return matrix


async def _bulk_insert(
    conn: AsyncConnection,
    model: type,
    path: Path,
    row_mapper: Callable[[dict], dict],
) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"missing kit file: {path}")
    total = 0
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        chunk: list[dict] = []
        for raw in reader:
            chunk.append(row_mapper(raw))
            if len(chunk) >= BULK_CHUNK:
                await conn.execute(insert(model), chunk)
                total += len(chunk)
                chunk = []
        if chunk:
            await conn.execute(insert(model), chunk)
            total += len(chunk)
    return total


async def _apply_deferrals(conn: AsyncConnection, path: Path) -> int:
    """Keep only the latest deferral event per donor (later event replaces earlier one)."""
    if not path.is_file():
        raise FileNotFoundError(f"missing kit file: {path}")
    latest: dict[str, tuple[str, str | None, int | None]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            donor_id = raw["donor_id"].strip()
            event_at = raw["event_at"].strip()
            defer_until = _opt_text(raw["defer_until"])
            defer_days = _opt_int(raw["defer_days"])
            current = latest.get(donor_id)
            if current is None or event_at >= current[0]:
                latest[donor_id] = (event_at, defer_until, defer_days)
    rows = [
        {
            "b_donor_id": donor_id,
            "b_defer_until": defer_until,
            "b_defer_days": defer_days,
        }
        for donor_id, (_event_at, defer_until, defer_days) in latest.items()
    ]
    if rows:
        await conn.execute(
            update(Donor)
            .where(Donor.donor_id == bindparam("b_donor_id"))
            .values(
                defer_until=bindparam("b_defer_until"),
                defer_days=bindparam("b_defer_days"),
            ),
            rows,
        )
    return len(rows)


async def load_kit_data(settings, engine: AsyncEngine) -> KitData:
    """Load all kit inputs once at startup; kit tables are cleared first so restarts are safe."""
    kit_path = Path(getattr(settings, "KIT_PATH", None) or getattr(settings, "kit_path", None))
    if not kit_path.is_dir():
        raise FileNotFoundError(f"kit path does not exist: {kit_path}")

    compat = _read_yaml(kit_path / "compat.yaml")
    rules = _read_yaml(kit_path / "rules.yaml")
    travel_area_to_hospital = _read_travel_matrix(kit_path / "travel_area_to_hospital.csv")
    travel_center_to_hospital = _read_travel_matrix(kit_path / "travel_center_to_hospital.csv")
    travel_area_to_center = _read_travel_matrix(kit_path / "travel_area_to_center.csv")

    async with engine.begin() as conn:
        await conn.execute(delete(DonorHistory))
        await conn.execute(delete(Donor))
        await conn.execute(delete(Hospital))
        await conn.execute(delete(Center))
        await _bulk_insert(conn, Donor, kit_path / "donors.csv", _donor_row)
        await _bulk_insert(conn, Hospital, kit_path / "hospitals.csv", _hospital_row)
        await _bulk_insert(conn, Center, kit_path / "centers.csv", _center_row)
        await _bulk_insert(
            conn,
            DonorHistory,
            kit_path / "history" / "responses.csv",
            _history_row,
        )
        await _apply_deferrals(conn, kit_path / "donor_events.csv")

    return KitData(
        compat=compat,
        rules=rules,
        travel_area_to_hospital=travel_area_to_hospital,
        travel_center_to_hospital=travel_center_to_hospital,
        travel_area_to_center=travel_area_to_center,
    )
