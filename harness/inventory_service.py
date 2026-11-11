"""Center Inventory service (local practice/evaluation mock, stdlib HTTP). The only way a team's system can move center stock to a hospital,
so the harness can count stock units with ground truth exactly like the baselines do.
  GET  /inventory  -> {"sim_time", "items": [{center_id, blood_group, product, units, expires_at, expires_sim_min}]}
  POST /inventory/dispatch {dispatch_id, request_id, center_id, blood_group, product, units}
       201 {dispatch_id, units, eta_sim_min}   same dispatch_id + same body again -> 200 with the same result
       404 unknown_request | 409 insufficient_stock / request_cancelled (nothing taken) | 400 validation_error
       422 incompatible (counted as a SAFETY error) | 422 product_mismatch | 422 idempotency_key_reuse
Units leave first-expiry-first within the chosen (center, group, product) and reach the hospital after
10 min handling + center->hospital travel. Stock is replenished every sim midnight (as in the baselines).
Practice mode (python -m harness.inventory_service --kit participant_kit): the service does not know the team's
requests, so it accepts any request_id, checks stock and idempotency only, and needs "hospital_id" in the body for an ETA.
Compatibility is checked only in the evaluation run."""
import json, sys, os, threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from harness import restock as H
from harness.simconfig import *
from harness.common import make_server

HANDLING_MIN = 10.0


class Inventory:
    def __init__(self, W, dm, clock, R, seed=1, practice=False):
        self.W, self.dm, self.clock, self.R, self.practice = W, dm, clock, R, practice
        self.rng = np.random.default_rng(seed + 1); self.results = {}
        self.units_dispatched = 0; self.incompatible = 0; self.expired_units = 0

    @property
    def stock(self):
        return self.dm.S.stock

    def new_day(self, day):
        with self.dm.lock:
            self.expired_units += sum(b[0] for bl in self.stock.values() for b in bl if b[0] > 0 and b[1] <= day)
            H.restock(self.W, self.dm.S, self.R, self.rng, day)

    def items(self):
        now_day = self.clock.now() / 1440.0; out = []
        with self.dm.lock:
            for (c, g, p), bl in sorted(self.stock.items()):
                for units, exp in sorted(bl, key=lambda b: b[1]):
                    if units > 0 and exp > now_day:
                        out.append(dict(center_id=self.W.center_ids[c], blood_group=GROUPS[g], product=PRODUCTS[p], units=int(units),
                                        expires_at=(SNAPSHOT + timedelta(days=float(exp))).strftime("%Y-%m-%dT%H:%M:%S"),
                                        expires_sim_min=round(exp * 1440.0, 1)))
        return out

    def dispatch(self, b):
        W, dm = self.W, self.dm
        try:
            did, rid, units = str(b["dispatch_id"]), str(b["request_id"]), int(b["units"])
            c, g, p = W.center_ids.index(b["center_id"]), GROUPS.index(b["blood_group"]), PRODUCTS.index(b["product"])
            assert units >= 1
        except Exception:
            return 400, {"error": {"code": "validation_error", "message": "dispatch_id, request_id, center_id, blood_group, product, units>=1"}}
        sig = (rid, c, g, p, units)
        with dm.lock:
            if did in self.results:
                old_sig, res = self.results[did]
                if old_sig != sig: return 422, {"error": {"code": "idempotency_key_reuse", "message": "dispatch_id reused with a different body"}}
                return 200, res
            tr = dm.truth.get(rid)
            if tr is None and self.practice:
                hid = b.get("hospital_id")
                recipient_group = b.get("recipient_blood_group")
                if recipient_group not in GROUPS:
                    return 400, {"error": {"code": "validation_error", "message": "practice dispatch requires recipient_blood_group"}}
                tr = dict(h=W.hosp_ids.index(hid) if hid in W.hosp_ids else None,
                          g=GROUPS.index(recipient_group), p=p, cancelled=False)
            if tr is None: return 404, {"error": {"code": "unknown_request", "message": rid}}
            if tr["cancelled"]: return 409, {"error": {"code": "request_cancelled", "message": rid}}
            if p != tr["p"]: return 422, {"error": {"code": "product_mismatch", "message": f"request needs {PRODUCTS[tr['p']]}"}}
            if tr["g"] is not None and not W.compat[p, g, tr["g"]]:
                self.incompatible += 1
                return 422, {"error": {"code": "incompatible", "message": f"{GROUPS[g]} {PRODUCTS[p]} cannot go to {GROUPS[tr['g']]}"}}
            now = self.clock.now(); now_day = now / 1440.0
            blocks = sorted([blk for blk in self.stock.get((c, g, p), []) if blk[0] > 0 and blk[1] > now_day], key=lambda blk: blk[1])
            avail = sum(blk[0] for blk in blocks)
            if avail < units: return 409, {"error": {"code": "insufficient_stock", "message": f"available={avail}"}}
            left = units
            for blk in blocks:
                k = min(blk[0], left); blk[0] -= k; left -= k
                if not left: break
            eta = None if tr["h"] is None else now + HANDLING_MIN + float(W.t_ch[c, tr["h"]])
            if not self.practice:
                for _ in range(units):
                    dm.donations.append(dict(request_id=rid, donor_id=None, supply_min=eta, cancel_check=None, source="stock"))
            self.units_dispatched += units
            res = dict(dispatch_id=did, units=units, eta_sim_min=None if eta is None else round(eta, 2)); self.results[did] = (sig, res)
            return 201, res


def serve(inv, port=9300):
    class Hn(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _s(self, c, b):
            r = json.dumps(b, ensure_ascii=False).encode(); self.send_response(c); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(r))); self.end_headers(); self.wfile.write(r)
        def do_GET(self):
            u = urlparse(self.path).path
            if u == "/health": return self._s(200, {"ok": True})
            if u == "/inventory": return self._s(200, {"sim_time": round(inv.clock.now(), 2), "items": inv.items()})
            self._s(404, {"error": {"code": "not_found", "message": ""}})
        def do_POST(self):
            if urlparse(self.path).path != "/inventory/dispatch": return self._s(404, {"error": {"code": "not_found", "message": ""}})
            try: b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except Exception: return self._s(400, {"error": {"code": "validation_error", "message": "bad json"}})
            self._s(*inv.dispatch(b))
    srv = make_server(port, Hn); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv


if __name__ == "__main__":
    import argparse, types
    from harness import world, physics
    from harness.common import VClock, Scheduler, DEFAULT_SPEED
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=9300); ap.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    ap.add_argument("--kit", default="participant_kit")
    a = ap.parse_args()
    W = world.build_world(a.kit); clock = VClock(a.speed)
    dm = types.SimpleNamespace(S=world.load_state(W, a.kit), lock=threading.Lock(), truth={}, donations=[])
    inv = Inventory(W, dm, clock, physics.Rules(RULES_V1), practice=True); inv.new_day(0)
    sched = Scheduler(clock); sched.start()
    for d in range(1, 60): sched.at(d * 1440.0, lambda d=d: inv.new_day(d))
    serve(inv, a.port); print(f"practice Inventory on :{a.port} speed x{a.speed}"); threading.Event().wait()
