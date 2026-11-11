"""Local practice runner: python -m harness.runner --team http://127.0.0.1:8000 --scenario P-normal
Drives your API with the practice scenario stream, serves the Gateway+Donor Simulator (practice
model), Travel and Inventory on localhost, and scores your run against the shipped practice
baselines. Everything runs on your laptop — no tokens, no cloud services, no cost."""
import argparse, json, math, os, sys, time, threading
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from harness import world, practice_scenarios as SC, physics, model_api
from harness.simconfig import *
from harness.common import VClock, http, header, DEFAULT_SPEED
from harness.mock_gateway import Gateway, serve
from harness.donor_sim import DonorModel
from harness import scoring, travel_service, inventory_service

HOSPITAL = {"Authorization": "Bearer hospital-token"}
COORDINATOR = {"Authorization": "Bearer coordinator-token"}
APPROVE_DELAY_MIN = 10.0     # the practice coordinator reviews a pending_review request after this many sim-minutes
MAX_ATTEMPTS, MAX_RETRY_WAIT_S = 5, 5.0
DEFAULT_BASELINES = os.path.join(os.path.dirname(__file__), "practice_baselines.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True); ap.add_argument("--scenario", default="P-normal"); ap.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    ap.add_argument("--mode", default="sim", choices=["sim", "echo"]); ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--kit", default="participant_kit"); ap.add_argument("--baselines", default=DEFAULT_BASELINES)
    ap.add_argument("--out", default="run_out")
    ap.add_argument("--gateway-port", type=int, default=9100); ap.add_argument("--travel-port", type=int, default=9200)
    ap.add_argument("--inventory-port", type=int, default=9300)
    ap.add_argument("--max-requests", type=int, default=0); ap.add_argument("--drain-min", type=float, default=SC.DRAIN_MIN)
    ap.add_argument("--sched-workers", type=int, default=128, help="callback worker pool size (0 = deliver callbacks one at a time)")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); T = a.team.rstrip("/")
    spec = SC.SCENARIOS[a.scenario]
    W = world.build_world(a.kit)
    R = physics.Rules(RULES_V1); P = SC.shifted_params(a.seed)
    S = world.load_state(W, a.kit); dm = DonorModel(W, S, R, P, a.seed)
    clock = VClock(a.speed); gw = Gateway(clock, a.mode, a.seed, dm, os.path.join(a.out, "gateway_log.jsonl"), sched_workers=a.sched_workers)
    inv = inventory_service.Inventory(W, dm, clock, R, a.seed)
    serve(gw, a.gateway_port); travel_service.serve(clock, a.travel_port); inventory_service.serve(inv, a.inventory_port)
    for c in spec["chaos"]:
        if c["kind"] == "outage": gw.sched.at(c["start_h"] * 60, lambda: gw.chaos.update(mode="outage", until_min=clock.now() + 120))
        if c["kind"] == "dup_callbacks": gw.chaos.update(mode="dup")
        if c["kind"] == "out_of_order": gw.chaos.update(mode="ooo")
    stream = SC.build_stream(W, a.scenario, a.seed)
    if a.max_requests: stream = stream[: a.max_requests]
    # the run ends at the horizon; unmet requests whose deadline is later are censored
    horizon = (stream[-1]["t"] if a.max_requests and stream else spec["days"] * 1440.0) + a.drain_min
    # nightly restock, day 0 restocked at start (same as the shipped practice baselines)
    inv.new_day(0)
    for d in range(1, int(math.ceil(horizon / 1440.0)) + 1):
        gw.sched.at(d * 1440.0, lambda d=d: inv.new_day(d))
    created = {}; lock = threading.Lock()

    def call(method, path, body, auth, key=None):
        """A well-behaved client: retries 429/503/network errors, honouring Retry-After (wall seconds, capped)."""
        for attempt in range(MAX_ATTEMPTS):
            h = {**auth, "X-Sim-Time": f"{clock.now():.2f}"}
            if key: h["Idempotency-Key"] = key
            code, j, hd = http(method, T + path, body, h)
            if code not in (0, 429, 503) or attempt == MAX_ATTEMPTS - 1: return code, j
            try: wait = float(header(hd, "Retry-After", 1))
            except ValueError: wait = 1.0
            time.sleep(min(max(wait, 0.1), MAX_RETRY_WAIT_S))

    def submit(rq):
        body = dict(hospital_id=rq.get("hosp_id") or W.hosp_ids[rq["h"]], blood_group=GROUPS[rq["g"]], product=PRODUCTS[rq["p"]],
                    units=rq["units"], urgency=URGENCY[rq["urg"]])
        code, j = call("POST", "/requests", body, HOSPITAL, key=f"{rq['rid']}-s{a.seed}")   # unique per run
        ok = code in (200, 201) and j and "request_id" in j
        if ok: dm.register(j["request_id"], rq["h"], rq["g"], rq["p"], rq["units"], rq["urg"], clock.now(), rq["rid"])
        with lock: created[rq["rid"]] = dict(team_id=j["request_id"] if ok else None, code=code, status0=(j or {}).get("status") if ok else None,
                                             rq=rq, t=clock.now(), approved=False)
        if not ok: return
        rid = j["request_id"]
        if j.get("status") == "pending_review" and not rq.get("abuse"):      # the coordinator approves real traffic, never the fake one
            time.sleep(clock.wall_for(clock.now() + APPROVE_DELAY_MIN))
            c2, _ = call("POST", f"/requests/{rid}/approve", {}, COORDINATOR)
            with lock: created[rq["rid"]]["approved"] = c2 in (200, 201)
        if rq.get("amend"):
            amend = rq["amend"]
            if amend.get("cancel"):
                time.sleep(clock.wall_for(clock.now() + 15))
                call("POST", f"/requests/{rid}/cancel", {}, HOSPITAL)
                dm.truth[rid]["cancelled"] = True
            elif amend.get("urg") is not None:
                target_min = float(amend["at_min"])
                delay = clock.wall_for(target_min)
                if delay > 0:
                    time.sleep(delay)
                new_urgency = URGENCY[int(amend["urg"])]
                c3, _ = call("POST", f"/requests/{rid}/amend", {"urgency": new_urgency}, HOSPITAL)
                if c3 in (200, 201):
                    dm.truth[rid]["urg"] = int(amend["urg"])
                    rq["urg"] = int(amend["urg"])

    print(f"practice scenario {a.scenario}: {len(stream)} requests, speed x{a.speed}", flush=True)
    ths = []
    for rq in stream:
        w = clock.wall_for(rq["t"])
        if w > 0: time.sleep(w)
        th = threading.Thread(target=submit, args=(rq,), daemon=True); th.start(); ths.append(th)
    for th in ths: th.join(30)
    time.sleep(clock.wall_for(horizon))
    # collect team-reported state
    reported = {}
    for rid, c in created.items():
        if c["team_id"]:
            code, j, _ = http("GET", f"{T}/requests/{c['team_id']}", None, HOSPITAL); reported[rid] = j if code == 200 else None
    res = scoring.score(created, dm, gw, inv, reported, R, a.baselines, a.scenario, horizon)
    lag = gw.sched.lag_stats()
    # valid_run: the harness kept up with its own schedule (team slowness shows up in "start" lag and is the team's own cost)
    res["summary"]["harness"] = dict(speed=a.speed, wall_s=round(time.time() - clock.t0, 1), callback_lag_sim_min=lag,
                                     valid_run=lag["dispatch"]["p95"] <= 0.5)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1, ensure_ascii=False, default=float)
    print(json.dumps(res["summary"], indent=1, ensure_ascii=False, default=float))
    print("note: practice scores use the shipped practice calibration and baselines; evaluation runs on a hidden catalogue.")


if __name__ == "__main__":
    main()
