"""Notification Gateway + Donor Simulator in one process (stdlib only).
mode: echo  -> practice Donor Echo (fixed accept prob, random delay, no behaviour model)
      sim   -> practice Donor Simulator driven by the practice model (harness/model_api.py)
Public: GET /clock -> {"sim_time", "epoch", "speed"}  (the official simulation clock for teams)
Admin: POST /admin/chaos {"mode": "normal|high_latency|dup|ooo|ratelimit|outage|silent", "until_min": ..., "limit_per_min": 60}
"""
import json, random, sys, os, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from harness.common import VClock, Scheduler, http, make_server, DEFAULT_SPEED
from harness.simconfig import SIM_EPOCH_ISO


class Gateway:
    def __init__(self, clock, mode="echo", seed=1, donor_model=None, log_path="gateway_log.jsonl", admin_token="admin", sched_workers=128):
        self.clock, self.mode, self.rng = clock, mode, random.Random(seed)
        self.sched = Scheduler(clock, sched_workers); self.sched.start()
        self.seen = {}; self.chaos = {"mode": "normal", "until_min": 1e18, "limit_per_min": 120}
        self.sent_times = []; self.lock = threading.Lock(); self.log = open(log_path, "w"); self.donor_model = donor_model
        self.admin_token = admin_token; self.pending = {}   # (request_id, donor_id) -> state
        self.count_by_request = {}; self.wave_by_request = {}

    # ---------- logging
    def _log(self, **kw):
        kw["wall"] = None; kw["sim"] = round(self.clock.now(), 2)
        with self.lock: self.log.write(json.dumps(kw, ensure_ascii=False) + "\n"); self.log.flush()

    def _cb(self, url, payload, dup=False, delay=0.0):
        # audit log of every outgoing callback (incl. duplicates), for smoke coverage checks
        self._log(kind="cb", path=url.rsplit("/callbacks/", 1)[-1], dup=dup or None, **payload)
        def fire():
            http("POST", url, payload, timeout=5)
        self.sched.at(self.clock.now() + delay, fire)
        if dup or (self.chaos["mode"] == "dup" and self.rng.random() < 0.5):
            self.sched.at(self.clock.now() + delay + self.rng.uniform(0.1, 2), fire)

    def _status(self, n, status, delay):
        self._cb(n["callback_url"] + "/callbacks/gateway-status", dict(event_id=f"ev-{uuid.uuid4().hex[:12]}", notification_id=n["notification_id"],
                 request_id=n["request_id"], donor_id=n["donor_id"], status=status, sim_time=round(self.clock.now() + delay, 2)), delay=delay)

    # ---------- main entry
    def send(self, n):
        now = self.clock.now(); c = self.chaos
        if now > c["until_min"]: c["mode"] = "normal"
        if c["mode"] == "outage": return 503, {"error": {"code": "unavailable", "message": "gateway down"}}, {}
        if c["mode"] == "ratelimit":
            self.sent_times = [t for t in self.sent_times if now - t < 1.0]
            if len(self.sent_times) >= c["limit_per_min"]:
                return 429, {"error": {"code": "rate_limited", "message": "slow down"}}, {"Retry-After": "1"}
            self.sent_times.append(now)
        for k in ("notification_id", "donor_id", "template", "request_id", "callback_url"):
            if k not in n: return 400, {"error": {"code": "validation_error", "message": f"missing {k}"}}, {}
        if n["template"] not in ("request_wave", "confirmed", "not_needed", "cancelled", "reminder"):
            return 400, {"error": {"code": "validation_error", "message": "bad template"}}, {}
        with self.lock:
            if n["notification_id"] in self.seen: return 409, {"error": {"code": "duplicate_notification", "message": "already used"}}, {}
            self.seen[n["notification_id"]] = True
            self.count_by_request[n["request_id"]] = self.count_by_request.get(n["request_id"], 0) + 1
            if n["template"] == "request_wave":
                self.wave_by_request[n["request_id"]] = self.wave_by_request.get(n["request_id"], 0) + 1
        self._log(kind="msg", **{k: n[k] for k in ("notification_id", "donor_id", "template", "request_id")})
        lat = {"high_latency": self.rng.uniform(4, 12)}.get(c["mode"], self.rng.uniform(0.02, 0.1))
        if c["mode"] == "ooo":
            self._status(n, "delivered", lat); self._status(n, "sent", lat + self.rng.uniform(0.1, 1)); 
        else:
            self._status(n, "queued", 0.0); self._status(n, "sent", lat * .5); self._status(n, "delivered", lat)
        if c["mode"] != "silent":
            self.donor_react(n, lat)
        return 202, {"notification_id": n["notification_id"], "status": "accepted"}, {}

    # ---------- donor behaviour
    def donor_react(self, n, lat):
        key = (n["request_id"], n["donor_id"]); t = n["template"]
        if self.mode == "sim":
            self.donor_model.react(self, n, lat, key); return
        if t == "request_wave":
            if self.rng.random() < 0.55:
                d = lat + self.rng.lognormvariate(1.5, 0.8)
                self._cb(n["callback_url"] + "/callbacks/donor-response", dict(event_id=f"ev-{uuid.uuid4().hex[:12]}", notification_id=n["notification_id"],
                         request_id=n["request_id"], donor_id=n["donor_id"], response="accepted", sim_time=round(self.clock.now() + d, 2)), delay=d)
                self.pending[key] = n
        elif t == "confirmed" and key in self.pending:
            base = lat + self.rng.uniform(10, 40)
            for i, ev in enumerate(["en_route", "arrived", "screen_pass", "donated"]):
                dd = base * (i + 1) / 2 if i < 2 else base + 10 * i
                self._cb(n["callback_url"] + "/callbacks/donor-progress", dict(event_id=f"ev-{uuid.uuid4().hex[:12]}", request_id=n["request_id"], donor_id=n["donor_id"],
                         event=ev, sim_time=round(self.clock.now() + dd, 2)), delay=dd)


def make_handler(gw, travel=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, body, hdr=None):
            raw = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
            for k, v in (hdr or {}).items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            try: return json.loads(self.rfile.read(n) or b"{}")
            except Exception: return None
        def do_GET(self):
            if self.path == "/health": return self._send(200, {"ok": True, "sim_time": gw.clock.now(), "mode": gw.mode})
            if self.path == "/clock": return self._send(200, {"sim_time": round(gw.clock.now(), 3), "epoch": SIM_EPOCH_ISO, "speed": gw.clock.speed})
            if self.path == "/admin/stats": return self._send(200, {"messages": sum(gw.count_by_request.values()), "by_request": gw.count_by_request,
                                                                    "waves_by_request": gw.wave_by_request})
            self._send(404, {"error": {"code": "not_found", "message": ""}})
        def do_POST(self):
            b = self._body()
            if self.path == "/messages":
                if b is None: return self._send(400, {"error": {"code": "validation_error", "message": "bad json"}})
                c, j, h = gw.send(b); return self._send(c, j, h)
            if self.path == "/admin/chaos":
                if self.headers.get("Authorization") != f"Bearer {gw.admin_token}": return self._send(401, {"error": {"code": "unauthorized", "message": ""}})
                gw.chaos.update(b or {}); return self._send(200, gw.chaos)
            self._send(404, {"error": {"code": "not_found", "message": ""}})
    return H


def serve(gw, port=9100):
    srv = make_server(port, make_handler(gw)); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=9100); ap.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    a = ap.parse_args(); gw = Gateway(VClock(a.speed), "echo"); serve(gw, a.port); print(f"Gateway+Donor Echo on :{a.port} speed x{a.speed}")
    threading.Event().wait()
