"""Numerical evaluation of the local AI ranking module.

Prints two numbers used in docs/ai_module.md:

1. Holdout (80/20 split by donor_id): AUC and precision@20 of the
   P(accepted) model on historical responder rows.
2. Historical simulation: on 200 sampled requests, compare the mean
   messages-per-acceptance between travel_time ranking and ai_response
   ranking (simple wave simulation, cap 24 per wave). Lower is better —
   this maps directly to the competition spam metric.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.ai.features import BLOOD_GROUPS, DONATION_TYPES, DAYS_SINCE_LAST_DONATION_EMPTY, quiet_window_len  # noqa: E402

KIT = REPO_ROOT / "participant_kit"
MODEL_DIR = REPO_ROOT / "app" / "ai" / "model"
WAVE_CAP = 24
SIM_REQUESTS = 200
SEED = 42


def load_data():
    donors = pd.read_csv(KIT / "donors.csv", dtype={"donor_id": str})
    donors["sex_num"] = (donors["sex"] == "F").astype(float)
    donors["quiet_window_len"] = donors.apply(
        lambda r: quiet_window_len(r["quiet_start_hour"], r["quiet_end_hour"]), axis=1
    )
    donors["last_donation_at"] = pd.to_datetime(donors["last_donation_at"], errors="coerce")

    hist = pd.read_csv(
        KIT / "history" / "responses.csv",
        dtype={"request_id": str, "donor_id": str},
        parse_dates=["notified_at"],
    )
    hist = hist.sort_values(["donor_id", "notified_at", "request_id"], kind="stable").reset_index(drop=True)
    g = hist.groupby("donor_id", sort=False)
    hist["hist_notified"] = g.cumcount().astype(float)
    hist["hist_responded"] = g["responded"].cumsum() - hist["responded"]
    hist["hist_accepted"] = g["accepted"].cumsum() - hist["accepted"]
    hist["hist_donated"] = g["donated"].cumsum() - hist["donated"]
    delay = hist["response_delay_min"].fillna(0.0)
    hist["delay_sum_prior"] = g[delay.name].cumsum() - delay
    hist["mean_response_delay_min"] = hist["delay_sum_prior"] / hist["hist_responded"].clip(lower=1)
    prev_notified = g["notified_at"].shift(1)
    hist["days_since_last_notified"] = (
        (hist["notified_at"] - prev_notified).dt.total_seconds() / 86400.0
    ).fillna(0.0).clip(lower=0.0)
    hist["accept_rate"] = hist["hist_accepted"] / hist["hist_notified"].clip(lower=1)
    hist["donate_rate"] = hist["hist_donated"] / hist["hist_notified"].clip(lower=1)
    return donors, hist


def build_frame(donors, hist):
    df = hist[hist["responded"] == 1].merge(
        donors[["donor_id", "blood_group", "age", "weight_kg", "sex_num",
                "notified_90d", "last_donation_at", "quiet_window_len", "area_id"]],
        on="donor_id", how="left",
    )
    days_since_donation = (df["notified_at"] - df["last_donation_at"]).dt.total_seconds() / 86400.0
    df["days_since_last_donation"] = days_since_donation.fillna(DAYS_SINCE_LAST_DONATION_EMPTY).clip(lower=0.0)
    for group in BLOOD_GROUPS:
        df[f"bg_{group}"] = (df["blood_group"] == group).astype(float)
    for dtype in DONATION_TYPES:
        df[f"dt_{dtype}"] = 0.0
    return df.rename(columns={"sex_num": "sex"})


def holdout_evaluation(df, feature_order):
    rng = np.random.RandomState(SEED)
    donor_ids = df["donor_id"].unique()
    train_donors, test_donors = train_test_split(donor_ids, test_size=0.2, random_state=rng)
    train = df[df["donor_id"].isin(train_donors)]
    test = df[df["donor_id"].isin(test_donors)]

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(train[feature_order].to_numpy(), train["accepted"].to_numpy())
    y_true = test["accepted"].astype(int)
    y_score = pipeline.predict_proba(test[feature_order].to_numpy())[:, 1]

    auc = roc_auc_score(y_true, y_score)
    top_k = np.argsort(-y_score)[:20]
    precision_at_20 = float(y_true.iloc[top_k].mean())
    baseline = float(y_true.mean())
    return {"auc": auc, "precision@20": precision_at_20, "baseline_positive_rate": baseline,
            "n_test_rows": int(len(test))}


def historical_simulation(donors, hist, feature_order):
    pipeline = joblib.load(MODEL_DIR / "ranker.joblib")
    reqs = pd.read_csv(KIT / "history" / "requests.csv", dtype={"rid": str})
    rng = np.random.RandomState(SEED)
    sample = reqs.sample(n=SIM_REQUESTS, random_state=rng)
    req_lookup = sample.set_index("rid")["hospital_id"].to_dict()

    df = build_frame(donors, hist)
    travel = pd.read_csv(KIT / "travel_area_to_hospital.csv", dtype={"area_id": str})
    travel = travel.melt(id_vars="area_id", var_name="hospital_id", value_name="travel_min")

    sim = df[df["request_id"].isin(req_lookup.keys())].copy()
    sim["hospital_id"] = sim["request_id"].map(req_lookup)
    sim = sim.merge(travel, on=["area_id", "hospital_id"], how="left")
    sim["travel_min"] = sim["travel_min"].fillna(1e9)

    X = sim[feature_order].astype(float).to_numpy()
    sim["ai_score"] = pipeline.predict_proba(X)[:, 1]

    def messages_needed(group, key):
        ordered = group.sort_values(key, ascending=(key == "travel_min")).reset_index(drop=True)
        accepted_positions = np.flatnonzero(ordered["accepted"].to_numpy() == 1)
        if len(accepted_positions) == 0:
            return None
        last = int(accepted_positions[-1])
        waves = last // WAVE_CAP + 1
        return waves * WAVE_CAP  # messages actually sent (full waves)

    rows = []
    for rid, group in sim.groupby("request_id"):
        m_travel = messages_needed(group, "travel_min")
        m_ai = messages_needed(group, "ai_score")
        if m_travel is not None and m_ai is not None:
            rows.append((rid, m_travel, m_ai, int((group["accepted"] == 1).sum())))

    res = pd.DataFrame(rows, columns=["request_id", "travel_msgs", "ai_msgs", "accepted"])
    total_accepted = int(res["accepted"].sum())
    msgs_per_accept_travel = float(res["travel_msgs"].sum()) / total_accepted
    msgs_per_accept_ai = float(res["ai_msgs"].sum()) / total_accepted
    return {
        "n_requests": int(len(res)),
        "total_accepted": total_accepted,
        "travel_msgs_per_acceptance": msgs_per_accept_travel,
        "ai_msgs_per_acceptance": msgs_per_accept_ai,
        "improvement_pct": (msgs_per_accept_travel - msgs_per_accept_ai) / msgs_per_accept_travel * 100.0,
    }


def main():
    config = json.loads((MODEL_DIR / "feature_config.json").read_text(encoding="utf-8"))
    feature_order = config["features"]
    donors, hist = load_data()
    df = build_frame(donors, hist)

    holdout = holdout_evaluation(df, feature_order)
    print("== Holdout (80/20 by donor_id) ==")
    print(f"AUC = {holdout['auc']:.4f}")
    print(f"precision@20 = {holdout['precision@20']:.4f} (baseline positive rate = {holdout['baseline_positive_rate']:.4f}, n_test = {holdout['n_test_rows']})")

    sim = historical_simulation(donors, hist, feature_order)
    print("\n== Historical simulation (200 requests, wave cap 24) ==")
    print(f"requests with acceptances = {sim['n_requests']}, total accepted = {sim['total_accepted']}")
    print(f"travel_time: {sim['travel_msgs_per_acceptance']:.2f} messages per acceptance")
    print(f"ai_response: {sim['ai_msgs_per_acceptance']:.2f} messages per acceptance")
    print(f"improvement = {sim['improvement_pct']:.1f}% (positive = fewer messages)")


if __name__ == "__main__":
    main()
