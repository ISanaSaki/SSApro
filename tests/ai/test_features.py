"""Tests for the feature engineering shared by training and inference."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ai.features import (  # noqa: E402
    BLOOD_GROUPS, build_donor_features, ordered_feature_vector, quiet_window_len,
)


def test_quiet_window_len():
    assert quiet_window_len(0, 0) == 0.0
    assert quiet_window_len(1, 5) == 4.0
    assert quiet_window_len(22, 7) == 9.0  # crosses midnight: 24 - 22 + 7


def test_build_donor_features_numeric_and_one_hot():
    donor = {
        "donor_id": "D1", "blood_group": "AB-", "sex": "F", "age": 30, "weight_kg": 62.5,
        "notified_90d": 2, "quiet_start_hour": 22, "quiet_end_hour": 7,
        "last_donation_at": "", "last_donation_type": "plasma",
    }
    feats = build_donor_features(donor, sim_time=0.0)
    assert feats["sex"] == 1.0
    assert feats["age"] == 30.0
    assert feats["weight_kg"] == 62.5
    assert feats["notified_90d"] == 2.0
    assert feats["bg_AB-"] == 1.0
    assert sum(feats[f"bg_{g}"] for g in BLOOD_GROUPS) == 1.0
    assert feats["dt_plasma"] == 1.0
    assert feats["days_since_last_donation"] == 999.0  # empty -> sentinel
    assert feats["quiet_window_len"] == 9.0


def test_build_donor_features_history_defaults_and_rates():
    donor = {"donor_id": "D2", "blood_group": "O+", "sex": "M", "age": 25, "weight_kg": 70.0}
    feats = build_donor_features(donor)
    for key in ("hist_notified", "hist_responded", "hist_accepted", "hist_donated",
                "accept_rate", "donate_rate", "mean_response_delay_min", "days_since_last_notified"):
        assert feats[key] == 0.0

    stats = {"hist_notified": 10, "hist_accepted": 4, "accept_rate": 0.4, "donate_rate": 0.2,
             "mean_response_delay_min": 12.5, "days_since_last_notified": 3.0}
    feats = build_donor_features(donor, stats)
    assert feats["hist_notified"] == 10.0
    assert feats["accept_rate"] == 0.4
    assert 0.0 <= feats["accept_rate"] <= 1.0
    assert 0.0 <= feats["donate_rate"] <= 1.0


def test_ordered_feature_vector_projects_with_zero_fill():
    feats = {"a": 1.0, "b": 2.0}
    assert ordered_feature_vector(feats, ["b", "a", "c"]) == [2.0, 1.0, 0.0]
