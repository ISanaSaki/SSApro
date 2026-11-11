"""Black-box contract tests for the fixed API (mandatory features M1-M7 subset). python -m harness.contract_tests --team http://localhost:8000"""
import argparse, sys, os, json, threading, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from harness.common import http

BODY = dict(hospital_id="H01", blood_group="O-", product="red_cells", units=2, urgency="critical")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--team", required=True); a = ap.parse_args(); T = a.team.rstrip("/"); res = []
    def t(name, ok, info=""): res.append((name, bool(ok), info)); print(("PASS " if ok else "FAIL ") + name, info)
    A = {"Authorization": "Bearer hospital-token"}
    c, j, _ = http("GET", T + "/health"); t("health 200", c == 200)
    k = "k-" + uuid.uuid4().hex; c1, j1, _ = http("POST", T + "/requests", BODY, {**A, "Idempotency-Key": k}); t("create 201", c1 == 201 and j1 and "request_id" in j1, c1)
    c2, j2, _ = http("POST", T + "/requests", BODY, {**A, "Idempotency-Key": k}); t("same key+body -> 200 same id", c2 == 200 and j1 and j2 and j2.get("request_id") == j1.get("request_id"), c2)
    c3, j3, _ = http("POST", T + "/requests", {**BODY, "units": 3}, {**A, "Idempotency-Key": k}); t("same key, different body -> 422", c3 == 422 and (j3 or {}).get("error", {}).get("code") == "idempotency_key_reuse", c3)
    c4, _, _ = http("POST", T + "/requests", BODY, A); t("missing key -> 400", c4 == 400, c4)
    c5, _, _ = http("POST", T + "/requests", {**BODY, "blood_group": "Z+"}, {**A, "Idempotency-Key": "x" + k}); t("invalid group -> 400", c5 == 400, c5)
    c6, _, _ = http("POST", T + "/requests", {**BODY, "units": -1}, {**A, "Idempotency-Key": "y" + k}); t("negative units -> 400", c6 == 400, c6)
    ks = "conc-" + uuid.uuid4().hex; ids = []
    def go():
        c, j, _ = http("POST", T + "/requests", BODY, {**A, "Idempotency-Key": ks}); ids.append((c, (j or {}).get("request_id")))
    ths = [threading.Thread(target=go) for _ in range(20)]; [x.start() for x in ths]; [x.join() for x in ths]
    t("20 concurrent same key -> one request", len({i for _, i in ids if i}) == 1 and sum(1 for c, _ in ids if c == 201) == 1, f"created={sum(1 for c, _ in ids if c == 201)}")
    rid = (j1 or {}).get("request_id", "none")
    c7, j7, _ = http("GET", T + f"/requests/{rid}", None, A); t("GET request has counters", c7 == 200 and all(x in j7 for x in ("status", "needed", "confirmed", "en_route", "arrived", "fulfilled")), c7)
    c8, _, _ = http("GET", T + "/requests/nope", None, A); t("GET unknown -> 404", c8 == 404, c8)
    # S-amend contract (CR #7): urgency amendments must be accepted on a live request and refused on unknown/terminal ones
    ca1, ja1, _ = http("POST", T + f"/requests/{rid}/amend", {"urgency": "urgent"}, A); t("amend urgency -> 2xx", ca1 in (200, 201), ca1)
    ca2, _, _ = http("POST", T + "/requests/nope/amend", {"urgency": "urgent"}, A); t("amend unknown -> 404", ca2 == 404, ca2)
    # CR3 approval contract: only observable when the team holds the request in pending_review
    st0 = (j1 or {}).get("status")
    if st0 == "pending_review":
        cap, _, _ = http("POST", T + f"/requests/{rid}/approve", {}, {"Authorization": "Bearer coordinator-token"})
        _, jg, _ = http("GET", T + f"/requests/{rid}", None, A)
        t("approve pending_review -> 2xx and leaves pending", cap in (200, 201) and (jg or {}).get("status") != "pending_review", f"{cap}/{(jg or {}).get('status')}")
    else:
        print(f"SKIP approve (initial status {st0!r} is not pending_review; policy is team-specific)")
    ev = dict(event_id="ev-" + uuid.uuid4().hex, request_id=rid, donor_id="D00001", event="en_route", sim_time=1.0)
    http("POST", T + "/callbacks/donor-progress", ev); http("POST", T + "/callbacks/donor-progress", ev)
    _, j9, _ = http("GET", T + f"/requests/{rid}", None, A); t("duplicate callback event_id counted once", (j9 or {}).get("en_route", 0) <= 1, (j9 or {}).get("en_route"))
    ca, _, _ = http("POST", T + f"/requests/{rid}/cancel", {}, A); cb, _, _ = http("POST", T + f"/requests/{rid}/cancel", {}, A); t("cancel twice -> 200/200", ca == 200 and cb == 200, f"{ca}/{cb}")
    p = sum(1 for _, ok, _ in res if ok); print(f"\n{p}/{len(res)} passed"); sys.exit(0 if p == len(res) else 1)


if __name__ == "__main__":
    main()
