"""Train the local donor-response model and commit-ready artifacts.

Reads participant_kit/donors.csv (features) and participant_kit/history/
responses.csv (labels) and saves:

  app/ai/model/ranker.joblib      — sklearn Pipeline (StandardScaler + LogisticRegression)
  app/ai/model/feature_config.json — frozen feature names/order

The artifacts are committed so the demo runs without retraining.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.ai.features import (  # noqa: E402
    BLOOD_GROUPS, DONATION_TYPES, DAYS_SINCE_LAST_DONATION_EMPTY, quiet_window_len,
)

KIT = REPO_ROOT / "participant_kit"
MODEL_DIR = REPO_ROOT / "app" / "ai" / "model"

FEATURE_ORDER = [
    "age", "sex", "weight_kg", "notified_90d", "days_since_last_donation", "quiet_window_len",
    *[f"bg_{g}" for g in BLOOD_GROUPS],
    *[f"dt_{t}" for t in DONATION_TYPES],
    "hist_notified", "hist_responded", "hist_accepted", "hist_donated",
    "accept_rate", "donate_rate", "mean_response_delay_min", "days_since_last_notified",
]


def load_donors():
    donors = pd.read_csv(KIT / "donors.csv", dtype={"donor_id": str})
    donors["sex_num"] = (donors["sex"] == "F").astype(float)
    donors["quiet_window_len"] = donors.apply(
        lambda r: quiet_window_len(r["quiet_start_hour"], r["quiet_end_hour"]), axis=1
    )
    donors["last_donation_at"] = pd.to_datetime(donors["last_donation_at"], errors="coerce")
    return donors


def build_history_features():
    """Chronological per-donor aggregates; each row sees only prior rows (no leakage)."""
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
    return hist


def build_training_frame():
    donors = load_donors()
    hist = build_history_features()
    # Labels come only from rows where the donor responded (competition rule T7).
    df = hist[hist["responded"] == 1].merge(
        donors[
            ["donor_id", "blood_group", "age", "weight_kg", "sex_num",
             "notified_90d", "last_donation_at", "quiet_window_len"]
        ],
        on="donor_id", how="left",
    )
    days_since_donation = (df["notified_at"] - df["last_donation_at"]).dt.total_seconds() / 86400.0
    df["days_since_last_donation"] = days_since_donation.fillna(DAYS_SINCE_LAST_DONATION_EMPTY).clip(lower=0.0)

    for group in BLOOD_GROUPS:
        df[f"bg_{group}"] = (df["blood_group"] == group).astype(float)
    # last_donation_type is not available in history; leave the one-hot columns at 0.
    for dtype in DONATION_TYPES:
        df[f"dt_{dtype}"] = 0.0

    df = df.rename(columns={"sex_num": "sex"})
    return df[FEATURE_ORDER + ["accepted"]]


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    df = build_training_frame()
    X = df[FEATURE_ORDER].astype(float)
    y = df["accepted"].astype(int)

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(X.to_numpy(), y.to_numpy())

    joblib.dump(pipeline, MODEL_DIR / "ranker.joblib")
    config = {
        "features": FEATURE_ORDER,
        "model": "Pipeline(StandardScaler, LogisticRegression(max_iter=1000))",
        "label": "accepted (rows with responded==1 from history/responses.csv)",
        "trained_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_train_rows": int(len(df)),
        "positive_rate": float(y.mean()),
    }
    (MODEL_DIR / "feature_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    train_acc = float((pipeline.predict(X.to_numpy()) == y.to_numpy()).mean())
    print(f"trained on {len(df)} rows | positive rate {y.mean():.3f} | train accuracy {train_acc:.3f}")
    print(f"artifacts -> {MODEL_DIR / 'ranker.joblib'}, {MODEL_DIR / 'feature_config.json'}")


if __name__ == "__main__":
    main()
