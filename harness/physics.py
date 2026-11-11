"""Public world physics for the practice harness: rules, donor state and eligibility.
These are the same mechanics documented in participant_kit/rules.yaml and DATA_CARD.md —
the eligibility logic below is exactly what the evaluation harness applies."""
from dataclasses import dataclass
import numpy as np
from harness.simconfig import *

FAT_TAU = 7 * 1440.0


class Rules:
    def __init__(self, d):
        self.__dict__.update(d)


class State:
    def __init__(self, W, last_day, last_type, defer_day=None, tag=None, tag_day=None):
        n = len(W.g)
        self.last_day = last_day.astype(float).copy()
        self.last_type = last_type.astype(np.int8).copy()
        self.defer_day = np.full(n, -1e9) if defer_day is None else defer_day.copy()
        self.tag = np.zeros(n, np.int8) if tag is None else tag.copy()          # 0 none, 1 tattoo, 2 travel_risk
        self.tag_day = np.full(n, -1e9) if tag_day is None else tag_day.copy()
        self.busy = np.full(n, -1e9)
        self.fat = np.zeros(n); self.fat_t = np.zeros(n)
        self.notif_count = np.zeros(n, np.int32)
        self.beds = [np.full(b, -1e9) for b in W.beds0]
        self.stock = {}   # (center, group, product) -> list [units, expiry_day]

    def copy(self):
        s = State.__new__(State)
        for k, v in self.__dict__.items():
            if isinstance(v, np.ndarray):
                setattr(s, k, v.copy())
            elif k == "beds":
                s.beds = [b.copy() for b in v]
            elif k == "stock":
                s.stock = {kk: [b[:] for b in vv] for kk, vv in v.items()}
            else:
                setattr(s, k, v)
        return s


def eligible(W, S, R, ts, prod):
    """Base eligibility: age/weight/permanent exclusion/one-active-deferral, donation intervals
    (male/female whole blood, apheresis, cross-block) and temporary event deferrals
    (tattoo 180 d, travel_risk 90 d — see participant_kit/donor_events.csv)."""
    day = ts / 1440.0
    m = (W.age >= R.age_min) & (W.age <= R.age_max) & (W.weight >= R.weight_min_kg) & (~W.perm) & (S.defer_day <= day)
    since = day - S.last_day
    target = DON_TYPE[prod]
    same = np.where(target == 1, np.where(W.sex == 0, R.interval_wb_male, R.interval_wb_female), R.interval_apheresis)
    need = np.where(S.last_type == 0, 0, np.where(S.last_type == target, same, R.cross_block))
    m &= since >= need
    d1, d2 = R.event_deferral["tattoo"], R.event_deferral["travel_risk"]
    ev = np.where(S.tag == 1, d1, np.where(S.tag == 2, d2, 0))
    m &= ~((S.tag > 0) & ((day - S.tag_day) < ev))
    return m


def censor(done, t0, sla, horizon):
    """A request that is still unmet when the run ends, but whose deadline is after the end, has no
    outcome yet: it is left out of the SLA metrics. Practice and evaluation use the same rule."""
    met = done is not None and done <= sla
    return (not met) and horizon is not None and t0 + sla > horizon
