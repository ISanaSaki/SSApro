"""Ground-truth scoring. Normalised against Naive/Oracle baselines.  s = clip((T-N)/(O-N), 0, 1)
Real traffic and abuse traffic are scored separately: rejecting abuse is never a failure, mobilising for it is a leak.
The core score is out of 100: score_0_100 = 100 * safety * core.
The AI capability is OPTIONAL and never part of the core: it can only ADD bonus points on top
(judges enter the net rubric result 0..10 via --ai-points after applying the DECLARED.md
half-done-feature penalty). score_final = score_0_100 + safety * ai_points, so the practical
maximum is 110 and a team without an AI feature loses nothing (its cap is 100)."""
import json, numpy as np
from harness.simconfig import *
from harness.physics import censor


# A rate component whose Oracle is not at least this much better than Naive is dropped from the scenario
# (section 12.4 of the doc): with a tiny or reversed gap, (T-N)/(O-N) is noise, or rewards being worse than Naive.
MIN_GAP = 0.10
WEIGHTS = dict(sla=0.35, critical=0.25, spam=0.25, overfill=0.15)


def norm(t, n, o, lower_better=False, log=False):
    if t is None: return 0.0
    if log: t, n, o = np.log1p(t), np.log1p(n), np.log1p(o)
    if lower_better: t, n, o = -t, -n, -o
    return float(np.clip((t - n) / (o - n), 0, 1)) if o != n else 0.0


def score(created, dm, gw, inv, reported, R, baselines_path, scenario, horizon=None, ai_points=0.0):
    base = json.load(open(baselines_path)).get(scenario) if baselines_path else None
    per = []
    by_req, stock_by_req = {}, {}
    for d in dm.donations:
        if horizon is not None and d["supply_min"] > horizon: continue      # the run ended before this unit arrived
        by_req.setdefault(d["request_id"], []).append(d["supply_min"])
        if d.get("source") == "stock": stock_by_req[d["request_id"]] = stock_by_req.get(d["request_id"], 0) + 1
    for rid, c in created.items():
        rq = c["rq"]; tid = c["team_id"]; abuse = bool(rq.get("abuse"))
        if tid is None:
            per.append(dict(rid=rid, ok=False, units=rq["units"], sla_met=False, notif=0, urg=rq["urg"], cancelled=False, abuse=abuse,
                            censored=censor(None, rq["t"], R.sla[rq["urg"]], horizon),
                            unregistered=bool(rq.get("unregistered")), leaked=False, code=c["code"])); continue
        tr = dm.truth[tid]; sup = sorted(by_req.get(tid, []))
        done = (sup[rq["units"] - 1] - tr["t"]) if len(sup) >= rq["units"] else None
        waves = gw.wave_by_request.get(tid, 0)
        # abuse leak is decided by the team's policy, not by timing: a fake request is blocked only if it was rejected
        # or held in pending_review and nothing (donor waves, stock) was spent on it. An unregistered hospital must be rejected.
        leaked = abuse and (bool(rq.get("unregistered")) or c.get("status0") != "pending_review" or waves > 0 or len(sup) > 0)
        per.append(dict(rid=rid, ok=True, units=rq["units"], supplied=min(len(sup), rq["units"]), overfill=max(0, len(sup) - rq["units"]),
                        stock_units=stock_by_req.get(tid, 0), notif=gw.count_by_request.get(tid, 0), done_min=done,
                        sla_met=(done is not None and done <= R.sla[rq["urg"]]), censored=censor(done, tr["t"], R.sla[rq["urg"]], horizon),
                        urg=rq["urg"], cancelled=tr["cancelled"], abuse=abuse,
                        unregistered=bool(rq.get("unregistered")), leaked=leaked, status0=c.get("status0"), approved=c.get("approved")))
    real = [p for p in per if not p["abuse"]]
    live = [p for p in real if not p["cancelled"] and not p["censored"]]
    fake = [p for p in per if p["abuse"]]
    sup_total = sum(p.get("supplied", 0) for p in per)
    m = dict(n_requests=len(per), n_real=len(real), n_abuse=len(fake), n_censored=sum(1 for p in real if p["censored"]),
             create_failures=sum(1 for p in real if not p["ok"]),
             sla_all=float(np.mean([p["sla_met"] for p in live])) if live else 0.0,
             notif_per_unit=sum(p["notif"] for p in per) / max(sup_total, 1), overfill_units=sum(p.get("overfill", 0) for p in per),
             stock_units=inv.units_dispatched, stock_expired_units=inv.expired_units,
             ineligible_notifications=dm.ineligible_msgs, busy_notifications=dm.busy_msgs, total_messages=sum(gw.count_by_request.values()),
             incompatible_dispatches=inv.incompatible,
             pending_review_real=sum(1 for p in real if p.get("status0") == "pending_review"))
    if fake:
        m["abuse_leak_rate"] = sum(p["leaked"] for p in fake) / len(fake)
    for u, nme in enumerate(URGENCY):
        r = [p["sla_met"] for p in live if p["urg"] == u]; m[f"sla_{nme}"] = float(np.mean(r)) if r else None
    d = [p["done_min"] for p in live if p.get("done_min") is not None]; m["done_p50"] = float(np.percentile(d, 50)) if d else None; m["done_p95"] = float(np.percentile(d, 95)) if d else None
    # reported counters consistency (honesty check)
    mism = 0; chk = 0
    for rid, j in reported.items():
        if not j: continue
        chk += 1; t = next(p for p in per if p["rid"] == rid)
        if t["ok"] and j.get("fulfilled", 0) > t.get("supplied", 0) + 0: mism += 1
    m["reported_vs_truth_mismatch"] = mism / max(chk, 1)
    s = {}
    if base:
        N, O = base["naive"], base["oracle"]
        dropped = []
        for k, mk in (("sla", "sla_all"), ("critical", "sla_critical")):
            n_, o_ = N.get(mk), O.get(mk)
            if n_ is None or o_ is None or o_ - n_ < MIN_GAP: dropped.append(k); continue
            s[k] = norm(m[mk], n_, o_) if m[mk] is not None else 0.0
        s["spam"] = norm(m["notif_per_unit"], N["notif_per_unit"], O["notif_per_unit"], lower_better=True, log=True)
        s["overfill"] = norm(m["overfill_units"], N["overfill_units"], O["overfill_units"], lower_better=True, log=True)
        unsafe = (m["ineligible_notifications"] > 0.02 * max(m["total_messages"], 1) or m["incompatible_dispatches"] > 0
                  or m["create_failures"] > 0.1 * max(m["n_real"], 1))
        s["safety"] = 0.0 if unsafe else 1.0
        used = {k: w for k, w in WEIGHTS.items() if k not in dropped}
        core = sum(w * s[k] for k, w in used.items()) / sum(used.values())
        if fake:      # S-abuse: half the scenario is "block the fake traffic", half is "keep serving the real traffic"
            s["abuse_block"] = 1.0 - m["abuse_leak_rate"]
            core = 0.5 * core + 0.5 * s["abuse_block"]
        ai = float(min(max(ai_points, 0.0), 10.0))    # optional AI bonus, 0..10 (judges' net rubric result)
        s["ai_points"] = ai
        m["score_0_100"] = round(100 * s["safety"] * core, 1)
        m["ai_points"] = round(s["safety"] * ai, 1)
        m["score_final"] = round(m["score_0_100"] + m["ai_points"], 1)
        m["components"] = s; m["dropped_components"] = dropped
    return dict(summary=m, per_request=per)
