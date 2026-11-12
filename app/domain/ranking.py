from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class RankingContext:
    request: Any
    hospital: Any
    sim_min: float
    travel_minutes: dict = field(default_factory=dict)


@dataclass
class RankedDonor:
    donor_id: str
    score: float
    travel_minutes: float


@runtime_checkable
class DonorRankingStrategy(Protocol):
    name: str

    def rank(self, donors: list, context: RankingContext) -> list[RankedDonor]: ...


class TravelTimeRankingStrategy:
    name = "travel_time"

    def rank(self, donors: list, context: RankingContext) -> list[RankedDonor]:
        rows = []
        for d in donors:
            travel = context.travel_minutes.get(d.donor_id, float("inf"))
            rows.append((travel, getattr(d, "notified_90d", 0), d.donor_id))
        rows.sort()
        return [RankedDonor(donor_id=did, score=-travel, travel_minutes=travel) for travel, _, did in rows]
