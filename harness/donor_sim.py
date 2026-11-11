"""Practice Donor Simulator: reacts to gateway messages with the practice behaviour model (harness/model_api.py)."""
import uuid, threading, zlib
import numpy as np
from harness import physics as sc, model_api as hm
from harness.simconfig import *

# A donor who accepted but was never sent `confirmed` (or `not_needed`) stops waiting after this many sim-minutes.
ACCEPT_TTL_MIN = 120.0


class DonorModel:
    def __init__(self, W, S, R, P, seed=1):
        self.W, self.S, self.R, self.P = W, S, R, P
        self.seed = seed; self.truth = {}; self.pending = {}; self.lock = threading.Lock(); self.n_msgs = {}
        self.commit = {}         # donor_id -> (request_id, donor_id) of the donor's current commitment (rule A2)
        self.donations = []      # dicts: request_id, donor_id, supply_min, source
        self.ineligible_msgs = 0; self.busy_msgs = 0; self.events = 0

    def register(self, request_id, h, g, p, units, urg, t, scenario_rid=None):
        self.truth[request_id] = dict(h=h, g=g, p=p, units=units, urg=urg, t=t, cancelled=False, srid=scenario_rid or request_id)

    def _rng(self, tr, donor_id, template):
        """Randomness per (scenario request, donor, template, repeat): a donor reacts the same way to the same message
        whatever order the team's messages arrive in, so thread timing does not change the outcome of a run."""
        k = (tr["srid"], donor_id, template); n = self.n_msgs[k] = self.n_msgs.get(k, 0) + 1
        return np.random.default_rng([self.seed, zlib.crc32(f"{tr['srid']}|{donor_id}|{template}|{n}".encode())])

    def _emit(self, gw, n, path, payload, delay):
        payload.update(event_id=f"ev-{uuid.uuid4().hex[:12]}", request_id=n["request_id"], donor_id=n["donor_id"], sim_time=round(gw.clock.now() + delay, 2))
        gw._cb(n["callback_url"] + path, payload, delay=delay)

    @staticmethod
    def _active(st, now):
        if st["state"] == "accepted": return now <= st["resp_t"] + ACCEPT_TTL_MIN
        if st["state"] == "going": return now < st.get("end", 1e18)
        return False

    def react(self, gw, n, lat, key):
        W, S, R, P = self.W, self.S, self.R, self.P
        tr = self.truth.get(n["request_id"]); i = int(n["donor_id"][1:]) - 1
        if tr is None or not (0 <= i < len(W.g)): return
        now = gw.clock.now(); t = n["template"]
        with self.lock:
            if t == "request_wave":
                ts = now + lat; idx = np.array([i])
                if not sc.eligible(W, S, R, ts, tr["p"])[i] or not W.compat_vec[tr["p"]][tr["g"]][W.g[i]]:
                    self.ineligible_msgs += 1
                    self._emit(gw, n, "/callbacks/donor-response", dict(response="declined", reason="not_eligible"), lat + 1); return
                ck = self.commit.get(n["donor_id"])
                if ck is not None and ck != key and self._active(self.pending[ck], ts):
                    self.busy_msgs += 1      # A2: one active donation per donor; a committed donor turns other requests down
                    self._emit(gw, n, "/callbacks/donor-response", dict(response="declined", reason="busy"), lat + 1); return
                fat = S.fat[idx] * np.exp(-(ts - S.fat_t[idx]) / sc.FAT_TAU)
                rng = self._rng(tr, n["donor_id"], t)
                seen, acc, delay = hm.sample_response(rng, P, W, idx, ts, tr["urg"], fat, W.cmin[idx].astype(float))
                S.fat[i] = fat[0] + 1; S.fat_t[i] = ts; S.notif_count[i] += 1
                if seen[0]:
                    self._emit(gw, n, "/callbacks/donor-response", dict(response="accepted" if acc[0] else "declined"), lat + float(delay[0]))
                    if acc[0]:
                        self.pending[key] = dict(resp_t=ts + float(delay[0]), state="accepted"); self.commit[n["donor_id"]] = key
            elif t == "confirmed":
                st = self.pending.get(key)
                if not st or st["state"] != "accepted": return
                if not self._active(st, now):
                    st["state"] = "done"
                    self._emit(gw, n, "/callbacks/donor-progress", dict(event="no_show", reason="confirmation_timeout"), lat); return
                st["state"] = "going"; start0 = max(now + lat, st["resp_t"])
                tr_min = W.cmin[[i]].astype(float)
                rng = self._rng(tr, n["donor_id"], t)
                a, d, ps = hm.sample_arrival(rng, P, W, np.array([i]), tr_min)
                self._emit(gw, n, "/callbacks/donor-progress", dict(event="en_route"), start0 - now)
                if not a[0]:
                    self._emit(gw, n, "/callbacks/donor-progress", dict(event="no_show"), start0 - now + float(d[0])); st["state"] = "done"; return
                arr = start0 + float(d[0]); c = int(W.cidx[i]); j = int(np.argmin(S.beds[c])); start = max(arr, S.beds[c][j])
                o_h, c_h = W.open_h[c]
                if not (o_h == 0 and c_h == 24):
                    day = np.floor(start / 1440.0); tod = start - day * 1440.0
                    if tod < o_h * 60: start = day * 1440.0 + o_h * 60
                    elif tod + R.visit_min[tr["p"]] > c_h * 60: start = (day + 1) * 1440.0 + o_h * 60
                if start - arr > P.abandon_wait_min and rng.random() < 0.7:
                    self._emit(gw, n, "/callbacks/donor-progress", dict(event="no_show", reason="queue_abandoned"), arr - now); st["state"] = "done"; return
                self._emit(gw, n, "/callbacks/donor-progress", dict(event="arrived"), arr - now)
                if not ps[0]:
                    S.beds[c][j] = start + 10; self._emit(gw, n, "/callbacks/donor-progress", dict(event="screen_fail"), start - now); st["state"] = "done"; return
                end = start + R.visit_min[tr["p"]]; S.beds[c][j] = end
                self._emit(gw, n, "/callbacks/donor-progress", dict(event="screen_pass"), start - now)
                self._emit(gw, n, "/callbacks/donor-progress", dict(event="donated"), end - now)
                S.last_day[i] = start / 1440.0; S.last_type[i] = DON_TYPE[tr["p"]]
                st["end"] = end; st["supply"] = end + R.proc_min + float(W.t_ch[c, tr["h"]])
                self.donations.append(dict(request_id=n["request_id"], donor_id=n["donor_id"], supply_min=st["supply"], cancel_check=key, source="donor"))
            elif t in ("not_needed", "cancelled"):
                st = self.pending.get(key)
                if st and st["state"] in ("accepted", "going"):
                    if t == "cancelled" and st["state"] == "going" and "end" in st and st["end"] <= now: return
                    st["state"] = "stopped"
                    self.donations = [d for d in self.donations if d["cancel_check"] != key or st.get("end", 1e18) <= now]
