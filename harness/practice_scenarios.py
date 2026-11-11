"""PUBLIC practice scenarios. Each yields a request stream + chaos schedule.

These three practice scenarios let you exercise the full workflow locally. The evaluation
catalogue is larger and different (more scenarios, other hospitals/shifts, per-seed parameter
shifts), so treat practice scores as a smoke signal for your engineering, not a prediction."""
import numpy as np
from harness.simconfig import *
from harness.model_api import ModelParams

SCENARIOS = {
    "P-normal": dict(days=2, rate=18, shift={}, chaos=[]),
    "P-amend":  dict(days=2, rate=18, shift={}, chaos=[], amend_p=0.20),
    # fake hospital H98 is unregistered: it must be rejected; H09 receives an abusive over-demand burst
    "P-abuse":  dict(days=2, rate=18, shift={}, chaos=[], abuse=dict(hosp="H09", n=30), fake=dict(hosp_id="H98", n=6)),
}
# Practice traffic mix (published on purpose; evaluation traffic differs).
P_URG_P = [0.20, 0.35, 0.45]
P_PROD_P = [0.70, 0.12, 0.18]
P_HOUR_P = np.array([.6,.5,.4,.3,.3,.5,.9,1.5,2.4,3,3.1,3.1,2.9,3,3.1,2.9,2.7,2.3,1.9,1.5,1.1,.9,.7,.6]); P_HOUR_P = P_HOUR_P / P_HOUR_P.sum()

DRAIN_MIN = 240.0


def horizon(sc_name):
    return SCENARIOS[sc_name]["days"] * 1440.0 + DRAIN_MIN


def shifted_params(seed, scale=0.0):
    """Practice runs use one fixed calibration (no per-seed shift). Evaluation shifts part of
    its hidden calibration per seed — another reason practice scores only indicate ordering."""
    return ModelParams()


def build_stream(W, sc_name, seed):
    spec = SCENARIOS[sc_name]; rng = np.random.default_rng(seed)
    hw = W.hw / np.sum(W.hw)
    reqs = []
    for d in range(spec["days"]):
        n = rng.poisson(spec["rate"])
        for _ in range(n):
            urg = int(rng.choice(3, p=P_URG_P)); p = int(rng.choice(3, p=P_PROD_P))
            if p == 1 and urg == 2: urg = 1
            hr = int(rng.choice(24, p=P_HOUR_P))
            t = d * 1440.0 + hr * 60 + rng.uniform(0, 60)
            units = int(np.clip(rng.geometric(0.5), 1, 6)) if p == 0 else int(rng.integers(1, 4))
            reqs.append(dict(t=t, h=int(rng.choice(len(hw), p=hw)), g=int(rng.choice(8, p=GROUP_FREQ)), p=p, units=units, urg=urg))
    if "abuse" in spec:
        a = spec["abuse"]; h = W.hosp_ids.index(a["hosp"])
        for i in range(a["n"]):
            reqs.append(dict(t=600 + i * 0.3, h=h, g=7, p=0, units=8, urg=0, abuse=True))
    if "fake" in spec:   # unregistered hospital_id: must be rejected; h is a placeholder, never used for supply
        f = spec["fake"]
        for i in range(f["n"]):
            reqs.append(dict(t=900 + i * 3.0, h=0, hosp_id=f["hosp_id"], g=int(rng.choice(8, p=GROUP_FREQ)), p=0, units=2, urg=0,
                             abuse=True, unregistered=True))
    reqs.sort(key=lambda r: r["t"])
    for i, r in enumerate(reqs):
        r["rid"] = f"{sc_name}-{i:05d}"
        if spec.get("amend_p") and rng.random() < spec["amend_p"] and not r.get("abuse"):
            r["amend"] = dict(at_min=r["t"] + float(rng.uniform(10, 40)), urg=0 if r["urg"] else None, cancel=bool(rng.random() < .3))
    return reqs
