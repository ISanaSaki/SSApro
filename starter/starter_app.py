"""BloodNet starter service — a minimal but COMPLETE team-side base you can run and improve.

Standard library only (no pip installs needed). It implements the whole required contract:
idempotent request creation, validation, live inventory dispatch (FEFO, compatibility-safe),
naive donor outreach waves through the Gateway, idempotent callbacks, counters, amend/cancel/
approve — enough to pass the contract tests and finish a practice scenario. It is deliberately
naive (fixed radius, fixed waves, no prioritization): that is your starting point, not the
ceiling. Everything runs locally; the only "tokens" are the two fixed demo tokens below.

    python3 starter/starter_app.py            # from the Participant folder (reads .env if present)
    python3 -m harness.contract_tests --team http://127.0.0.1:8000
"""
import csv, json, os, threading, time, uuid, urllib.request, urllib.error
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- tiny .env loader (optional)
if os.path.isfile(os.path.join(BASE, ".env")):
    for line in open(os.path.join(BASE, ".env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

PORT = int(os.environ.get("PORT", "8000"))
SELF_URL = os.environ.get("SELF_URL", f"http://localhost:{PORT}").rstrip("/")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:9100").rstrip("/")
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:9300").rstrip("/")
KIT_PATH = os.path.join(BASE, os.environ.get("KIT_PATH", "participant_kit"))
HOSPITAL_TOKEN = os.environ.get("HOSPITAL_TOKEN", "hospital-token")        # fixed demo token, published in the kit
COORDINATOR_TOKEN = os.environ.get("COORDINATOR_TOKEN", "coordinator-token")

GROUPS = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
PRODUCTS = ["red_cells", "platelets", "plasma"]
URGENCY = ["critical", "urgent", "planned"]
SLA = {"critical": 90.0, "urgent": 240.0, "planned": 1440.0}
DON_TYPE = {"red_cells": 1, "platelets": 2, "plasma": 3}
INTERVAL = {"red_cells": {"M": 60, "F": 90}, "platelets": 14, "plasma": 14}
CROSS_BLOCK = 14
SNAPSHOT = datetime(2027, 1, 15)


def abo(g):
    return {"O": 0, "A": 1, "B": 2, "AB": 3}[g[:-1]], g.endswith("+")


def compatible(donor_g, recip_g, product):
    (da, dr), (ra, rr) = abo(donor_g), abo(recip_g)
    if product == "red_cells": return (da & ~ra) == 0 and dr <= rr
    if product == "platelets": return da == ra
    return (ra & ~da) == 0                        # plasma: reversed


# ---------------- kit data
def _read(name):
    with open(os.path.join(KIT_PATH, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

DONORS = _read("donors.csv")
HOSPITALS = {h["hospital_id"] for h in _read("hospitals.csv")}
TRAVEL = {}                                       # (area_id, hospital_id) -> minutes
with open(os.path.join(KIT_PATH, "travel_area_to_hospital.csv"), newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        a = row["area_id"]
        for h in HOSPITALS:
            try: TRAVEL[(a, h)] = float(row[h])
            except (KeyError, ValueError): pass
DEFER = {}                                        # donor_id -> defer_until datetime (latest event wins)
with open(os.path.join(KIT_PATH, "donor_events.csv"), newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try: DEFER[r["donor_id"]] = max(DEFER.get(r["donor_id"], datetime.min), datetime.fromisoformat(r["defer_until"]))
        except ValueError: pass
DONOR = {d["donor_id"]: d for d in DONORS}

# ---------------- state
LOCK = threading.Lock()
REQ = {}                                          # id -> request dict
IDEM = {}                                         # idempotency key -> (body_hash, code, payload)
SEEN_EV = set()
SIM = {"now": 0.0}                                # simulation minutes, refreshed from the Gateway clock


def now_sim():
    return SIM["now"]


def body_hash(b):
    return json.dumps(b, sort_keys=True)


def days_since(dt):
    return (dt - SNAPSHOT).total_seconds() / 86400.0


def donor_eligible(d, product, ts):
    """Base eligibility from the published rules (a starting point — refine it!)."""
    if d["permanently_excluded"] == "1": return False
    dv = DEFER.get(d["donor_id"])
    if dv is not None and ts / 1440.0 < days_since(dv): return False
    g = int(d["age"]); 
    if not (18 <= g <= 65) or float(d["weight_kg"]) < 50: return False
    last, typ = d["last_donation_at"], d["last_donation_type"]
    if not last: return True
    since = ts / 1440.0 - days_since(datetime.fromisoformat(last))
    target = DON_TYPE[product]
    if not typ: return True
    type_name = {1: "whole_blood", 2: "platelets", 3: "plasma"}[target]
    if typ == type_name:
        need = INTERVAL["red_cells"]["M" if d["sex"] == "M" else "F"] if product == "red_cells" else INTERVAL[product]
    else: need = CROSS_BLOCK
    return since >= need


def http_req(method, url, body=None, headers=None, timeout=8):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(); return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: j = json.loads(raw) if raw else None
        except Exception: j = None
        return e.code, j, dict(e.headers)
    except Exception as e:
        return 0, {"error": str(e)}, {}


def gw_post(url, body, tries=4):
    """POST with bounded 429/503 retry, honoring Retry-After. Network errors fail fast."""
    for i in range(tries):
        c, j, h = http_req("POST", url, body)
        if c not in (429, 503) or i == tries - 1: return c, j
        try: wait = float(h.get("Retry-After", 1))
        except ValueError: wait = 1.0
        time.sleep(min(max(wait, 0.2), 5))


def send_wave(r, radius):
    """One naive outreach wave: nearest compatible+eligible donors, capped."""
    cands = []
    for d in DONORS:
        t = TRAVEL.get((d["area_id"], r["hospital_id"]))
        if t is None or t > radius: continue
        if not compatible(d["blood_group"], r["blood_group"], r["product"]): continue
        if d["donor_id"] in r["notified"]: continue
        if not donor_eligible(d, r["product"], now_sim()): continue
        cands.append((t, d["donor_id"]))
    cands.sort()
    cap = min(max(r["needed"] * 8, 24), 80)
    for _, did in cands[:cap]:
        r["notified"].add(did)
        gw_post(GATEWAY_URL + "/messages", dict(notification_id="nt-" + uuid.uuid4().hex, donor_id=did,
                                                template="request_wave", request_id=r["id"], callback_url=SELF_URL))


def dispatch_stock(r):
    """Try to cover the remaining need from center stock: compatible groups, FEFO, idempotent."""
    need = r["needed"] - r["fulfilled"] - r["stock_inflight"]
    if need <= 0 or r["status"] in ("cancelled", "fulfilled"): return
    c, items, _ = http_req("GET", INVENTORY_URL + "/inventory")
    if c != 200 or not items: return
    picks = {}
    for it in sorted(items.get("items", []), key=lambda x: x.get("expires_sim_min", 1e18)):   # first-expiry-first-out
        if it["product"] != r["product"]: continue
        if not compatible(it["blood_group"], r["blood_group"], r["product"]): continue
        k = min(int(it["units"]), need - sum(picks.values()))
        if k > 0: picks[(it["center_id"], it["blood_group"])] = picks.get((it["center_id"], it["blood_group"]), 0) + k
        if sum(picks.values()) >= need: break
    for (center, group), units in picks.items():
        did = "dsp-" + uuid.uuid4().hex
        c, j = gw_post(INVENTORY_URL + "/inventory/dispatch",
                          dict(dispatch_id=did, request_id=r["id"], center_id=center, blood_group=group,
                               product=r["product"], units=units, hospital_id=r["hospital_id"],
                               recipient_blood_group=r["blood_group"]))
        if c in (200, 201):
            r["stock_inflight"] += units


def stop_outreach(r, template):
    for did in list(r["pending_accepted"]):
        gw_post(GATEWAY_URL + "/messages", dict(notification_id="nt-" + uuid.uuid4().hex, donor_id=did,
                                                template=template, request_id=r["id"], callback_url=SELF_URL))
    r["pending_accepted"].clear()


def finalize_if_done(r):
    if r["status"] == "active" and r["fulfilled"] >= r["needed"]:
        r["status"] = "fulfilled"; stop_outreach(r, "not_needed")


def background():
    """Clock refresh + wave scheduler + stock top-up."""
    while True:
        try:
            c, j, _ = http_req("GET", GATEWAY_URL + "/clock", timeout=3)
            if c == 200: SIM["now"] = float(j.get("sim_time", SIM["now"]))
        except Exception: pass
        with LOCK:
            for r in REQ.values():
                if r["status"] != "active": continue
                if now_sim() - r["last_wave"] >= 45 and r["waves"] < 4:
                    r["waves"] += 1; r["last_wave"] = now_sim()
                    send_wave(r, min(20.0 + 10.0 * r["waves"], 60.0))
                dispatch_stock(r)
        time.sleep(5)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try: return json.loads(self.rfile.read(n) or b"{}")
        except Exception: return None

    def _auth(self, token):
        return self.headers.get("Authorization") == f"Bearer {token}"

    def do_GET(self):
        u = urlparse(self.path).path
        if u == "/health": return self._send(200, {"ok": True, "service": "starter", "sim_time": round(now_sim(), 2)})
        m = u.startswith("/requests/") and u.count("/") == 2
        if m:
            if not self._auth(HOSPITAL_TOKEN): return self._send(401, {"error": {"code": "unauthorized", "message": "hospital token"}})
            rid = u.split("/")[2]
            with LOCK:
                r = REQ.get(rid)
                if r is None: return self._send(404, {"error": {"code": "not_found", "message": rid}})
                return self._send(200, dict(request_id=rid, status=r["status"], hospital_id=r["hospital_id"], blood_group=r["blood_group"],
                                            product=r["product"], urgency=r["urgency"], needed=r["needed"], confirmed=r["confirmed"],
                                            en_route=r["en_route"], arrived=r["arrived"], fulfilled=r["fulfilled"],
                                            stock_inflight=r["stock_inflight"], created_sim_min=round(r["created"], 2)))
        self._send(404, {"error": {"code": "not_found", "message": ""}})

    def do_POST(self):
        u = urlparse(self.path).path; b = self._body()
        if u == "/requests":
            if not self._auth(HOSPITAL_TOKEN): return self._send(401, {"error": {"code": "unauthorized", "message": "hospital token"}})
            key = self.headers.get("Idempotency-Key")
            if not key: return self._send(400, {"error": {"code": "missing_idempotency_key", "message": "Idempotency-Key required"}})
            if b is None: return self._send(400, {"error": {"code": "validation_error", "message": "bad json"}})
            bh = body_hash(b)
            with LOCK:
                if key in IDEM:
                    h0, code0, payload0 = IDEM[key]
                    if h0 != bh: return self._send(422, {"error": {"code": "idempotency_key_reuse", "message": "same key, different body"}})
                    return self._send(200, payload0)                     # idempotent replay
                err = None
                if b.get("hospital_id") not in HOSPITALS: err = (404, {"error": {"code": "unknown_hospital", "message": "unregistered hospital_id"}})
                elif b.get("blood_group") not in GROUPS or b.get("product") not in PRODUCTS or b.get("urgency") not in URGENCY:
                    err = (400, {"error": {"code": "validation_error", "message": "blood_group/product/urgency"}})
                else:
                    try: units = int(b.get("units"))
                    except (TypeError, ValueError): units = -1
                    if not 1 <= units <= 10: err = (400, {"error": {"code": "validation_error", "message": "units"}})
                if err: IDEM[key] = (bh, err[0], err[1]); return self._send(*err)
                rid = "R-" + uuid.uuid4().hex[:12]
                r = dict(id=rid, hospital_id=b["hospital_id"], blood_group=b["blood_group"], product=b["product"],
                         urgency=b["urgency"], needed=units, status="active", confirmed=0, en_route=0, arrived=0,
                         fulfilled=0, stock_inflight=0, created=now_sim(), sla=SLA[b["urgency"]], cancelled=False,
                         notified=set(), pending_accepted=set(), waves=0, last_wave=-1e9)
                REQ[rid] = r; IDEM[key] = (bh, 201, dict(request_id=rid, status=r["status"], needed=units))
                r["waves"] = 1; r["last_wave"] = now_sim()
            send_wave(r, 20.0); dispatch_stock(r)
            return self._send(201, dict(request_id=rid, status=r["status"], needed=units))
        parts = u.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "requests":
            rid, action = parts[1], parts[2]
            with LOCK:
                r = REQ.get(rid)
                if r is None: return self._send(404, {"error": {"code": "not_found", "message": rid}})
                if action == "amend":
                    urg = (b or {}).get("urgency")
                    if urg not in URGENCY: return self._send(400, {"error": {"code": "validation_error", "message": "urgency"}})
                    if r["status"] != "active": return self._send(409, {"error": {"code": "not_amendable", "message": r["status"]}})
                    r["urgency"] = urg; r["sla"] = SLA[urg]
                    return self._send(200, dict(request_id=rid, urgency=urg))
                if action == "cancel":
                    if r["status"] == "active": r["status"] = "cancelled"; stop_outreach(r, "cancelled")
                    return self._send(200, dict(request_id=rid, status=r["status"]))
                if action == "approve":
                    if not self._auth(COORDINATOR_TOKEN): return self._send(401, {"error": {"code": "unauthorized", "message": "coordinator token"}})
                    if r["status"] == "pending_review": r["status"] = "active"
                    return self._send(200, dict(request_id=rid, status=r["status"]))
            return self._send(404, {"error": {"code": "not_found", "message": ""}})
        if u == "/callbacks/gateway-status":
            ev = (b or {}).get("event_id")
            with LOCK:
                if ev and ev in SEEN_EV: return self._send(200, {"ok": True})
                if ev: SEEN_EV.add(ev)
            return self._send(200, {"ok": True})
        if u in ("/callbacks/donor-response", "/callbacks/donor-progress"):
            if b is None: return self._send(400, {"error": {"code": "validation_error", "message": "bad json"}})
            ev = b.get("event_id")
            with LOCK:
                if ev and ev in SEEN_EV: return self._send(200, {"ok": True})     # idempotent by event_id
                if ev: SEEN_EV.add(ev)
                r = REQ.get(b.get("request_id"))
                if r is None: return self._send(200, {"ok": True})
                did = b.get("donor_id")
                if u.endswith("donor-response"):
                    if b.get("response") == "accepted" and did not in r["pending_accepted"]:
                        r["pending_accepted"].add(did); r["confirmed"] += 1
                        gw_post(GATEWAY_URL + "/messages", dict(notification_id="nt-" + uuid.uuid4().hex, donor_id=did,
                                                                template="confirmed", request_id=r["id"], callback_url=SELF_URL))
                else:
                    e = b.get("event")
                    if e == "en_route": r["en_route"] += 1
                    elif e == "arrived": r["arrived"] += 1
                    elif e == "donated":
                        r["fulfilled"] += 1
                        r["pending_accepted"].discard(did); finalize_if_done(r)
                    elif e in ("no_show", "screen_fail"):
                        r["pending_accepted"].discard(did)
                return self._send(200, {"ok": True})
        self._send(404, {"error": {"code": "not_found", "message": ""}})


if __name__ == "__main__":
    threading.Thread(target=background, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"BloodNet starter service on :{PORT} (kit={KIT_PATH})")
    srv.serve_forever()
