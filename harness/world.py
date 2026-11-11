"""Rebuild the simulation world and the day-0 state from the published participant kit CSVs.
Everything here comes from files teams already have (donors/hospitals/centers/travel matrices/
donor_events). Latent donor traits used by the practice behaviour model are PRACTICE calibration
values drawn from a fixed public seed — the evaluation harness uses different, unpublished values."""
import os
from datetime import datetime
import numpy as np
import pandas as pd
from harness.simconfig import *
from harness import geo

PRACTICE_SEED = 424242   # public seed for practice latent traits (rel/health); NOT the evaluation values


def _abo_rh(g):
    name = GROUPS[g]
    return {"O": 0, "A": 1, "B": 2, "AB": 3}[name[:-1]], 1 if name[-1] == "+" else 0


def build_compat():
    """COMPAT[product][donor_group, recipient_group] -> bool (identical to participant_kit/compat.yaml)."""
    c = np.zeros((3, 8, 8), bool)
    for d in range(8):
        da, dr = _abo_rh(d)
        for r in range(8):
            ra, rr = _abo_rh(r)
            c[0, d, r] = (da & ~ra) == 0 and dr <= rr          # red cells
            c[1, d, r] = da == ra                               # platelets: ABO identical
            c[2, d, r] = (ra & ~da) == 0                        # plasma: reversed
    return c


class World:
    pass


def _days(iso):
    return (datetime.fromisoformat(str(iso)) - SNAPSHOT).total_seconds() / 86400


def build_world(kit):
    d = pd.read_csv(os.path.join(kit, "donors.csv"), keep_default_na=False)
    h = pd.read_csv(os.path.join(kit, "hospitals.csv"), keep_default_na=False)
    c = pd.read_csv(os.path.join(kit, "centers.csv"), keep_default_na=False)
    n = len(d)
    W = World()
    W.compat = build_compat()
    # hospitals / centers (km coordinates via the published origin)
    W.hosp_ids = h.hospital_id.tolist()
    W.center_ids = c.center_id.tolist()
    W.donor_ids = d.donor_id.tolist()
    W.hx, W.hy = geo.to_xy(h.lat.to_numpy(float), h.lon.to_numpy(float))
    W.cx, W.cy = geo.to_xy(c.lat.to_numpy(float), c.lon.to_numpy(float))
    W.beds0 = c.beds.to_numpy(int).tolist()
    W.open_h = list(zip(c.open_hour.astype(int), c.close_hour.astype(int)))
    W.hw = h.request_weight.to_numpy(float)
    W.hrural = np.array([(cr == "low" and w <= 0.2) for cr, w in zip(h.credit_level, W.hw)])
    W.hname = h.name.tolist()
    # published center->hospital travel matrix is the ground truth for ETAs
    tch = pd.read_csv(os.path.join(kit, "travel_center_to_hospital.csv"))
    W.t_ch = tch[W.hosp_ids].to_numpy(float)
    # donors: static published attributes
    W.g = np.array([GROUPS.index(x) for x in d.blood_group], np.int8)
    W.sex = (d.sex.astype(str) == "F").to_numpy(np.int8)            # 0 male, 1 female
    W.age = d.age.to_numpy(np.int16)
    W.weight = d.weight_kg.to_numpy(float)
    W.qs = d.quiet_start_hour.to_numpy(np.int16)
    W.qe = d.quiet_end_hour.to_numpy(np.int16)
    W.perm = d.permanently_excluded.to_numpy(bool) if hasattr(d, "permanently_excluded") else np.zeros(n, bool)
    lat, lon = d.lat.to_numpy(float), d.lon.to_numpy(float)
    W.dx, W.dy = geo.to_xy(lat, lon)
    # practice latent traits (public practice calibration — evaluation uses different values)
    rng = np.random.default_rng(PRACTICE_SEED)
    W.rel = rng.beta(2.2, 2.2, n)                # reliability in [0, 1]
    W.health = rng.normal(0, 1, n)               # screening health z-score
    # rural approximation: farther than 12 km from every published city centre
    cx = np.array([ci["x"] for ci in geo.CITIES]); cy = np.array([ci["y"] for ci in geo.CITIES])
    dist = np.hypot(W.dx[:, None] - cx[None, :], W.dy[:, None] - cy[None, :]).min(1)
    W.rural = dist > 12.0
    W.city = np.full(n, -1, np.int16)            # unused by the practice model (city offsets are 0)
    # travel tables for donors
    W.t_hosp = geo.route_minutes(W.dx[:, None], W.dy[:, None], W.hx[None, :], W.hy[None, :]).astype(np.float32)
    W.km_hosp = np.hypot(W.dx[:, None] - W.hx[None, :], W.dy[:, None] - W.hy[None, :]).astype(np.float32)
    t_dc = geo.route_minutes(W.dx[:, None], W.dy[:, None], W.cx[None, :], W.cy[None, :]).astype(np.float32)
    W.cidx = np.argmin(t_dc, axis=1)
    W.cmin = t_dc[np.arange(n), W.cidx]
    W.compat_vec = [[W.compat[p][:, g] for g in range(8)] for p in range(3)]
    return W


def load_state(W, kit):
    """Day-0 state: donation history, center stock, and temporary deferrals rebuilt from
    participant_kit/donor_events.csv (latest event per donor wins — see DATA_CARD.md)."""
    d = pd.read_csv(os.path.join(kit, "donors.csv"), keep_default_na=False)
    last = np.array([_days(x) if x else -1e9 for x in d.last_donation_at])
    typ = np.array([{"": 0, "whole_blood": 1, "platelets": 2, "plasma": 3}[x] for x in d.last_donation_type], np.int8)
    from harness.physics import State
    S = State(W, last, typ)
    inv = pd.read_csv(os.path.join(kit, "inventory.csv"))
    for r in inv.itertuples():
        key = (W.center_ids.index(r.center_id), GROUPS.index(r.blood_group), PRODUCTS.index(r.product))
        S.stock.setdefault(key, []).append([int(r.units), _days(r.expires_at)])
    ev_path = os.path.join(kit, "donor_events.csv")
    if os.path.isfile(ev_path):
        ev = pd.read_csv(ev_path)
        pos = {gid: i for i, gid in enumerate(W.donor_ids)}
        tag_of = {"tattoo": 1, "travel_risk": 2}
        applied = 0
        for r in ev.itertuples():                  # file is chronological; a later event replaces an older one
            i = pos.get(r.donor_id)
            if i is None or r.event not in tag_of:
                continue
            S.tag[i] = tag_of[r.event]; S.tag_day[i] = _days(r.event_at); applied += 1
        S.events_applied = applied
    return S
