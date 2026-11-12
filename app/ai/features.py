"""Feature engineering shared by model training and inference.

All feature names and their order are frozen in
``app/ai/model/feature_config.json``; both the training script and the
ranking strategy build feature dicts with :func:`build_donor_features`
and then order them according to the config.
"""
from __future__ import annotations

import datetime as dt

BLOOD_GROUPS = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
DONATION_TYPES = ["whole_blood", "plasma", "platelets"]
DAYS_SINCE_LAST_DONATION_EMPTY = 999.0

# Frozen kit epoch (CONTRACT section 4).
EPOCH = dt.datetime.fromisoformat("2027-01-15T00:00:00+03:30")


def _get(obj, name, default=None):
    """Attribute or mapping access — donors may be ORM objects or dicts."""
    if obj is None:
        return default
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict) and name in obj:
        return obj[name]
    return default


def _parse_minutes(value):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def quiet_window_len(quiet_start_hour, quiet_end_hour):
    start = int(quiet_start_hour or 0)
    end = int(quiet_end_hour or 0)
    if start == end:
        return 0.0
    if start > end:
        return float(24 - start + end)
    return float(end - start)


def days_since(value, reference):
    """Days between ``value`` and ``reference`` (both sim timestamps); empty -> sentinel."""
    parsed = _parse_minutes(value)
    ref = _parse_minutes(reference)
    if parsed is None or ref is None:
        return DAYS_SINCE_LAST_DONATION_EMPTY
    if parsed.tzinfo is not None and ref.tzinfo is None:
        ref = ref.replace(tzinfo=parsed.tzinfo)
    elif parsed.tzinfo is None and ref.tzinfo is not None:
        parsed = parsed.replace(tzinfo=ref.tzinfo)
    return max(0.0, (ref - parsed).total_seconds() / 86400.0)


def build_donor_features(donor, history_stats=None, *, sim_time=None):
    """Build the feature dict for one donor.

    ``history_stats`` is an optional dict of history-derived aggregates
    (hist_notified, hist_responded, hist_accepted, hist_donated,
    accept_rate, donate_rate, mean_response_delay_min,
    days_since_last_notified). Missing values default to 0/0.0.

    ``sim_time`` is the current sim clock in minutes; when provided, it is
    combined with the frozen kit epoch to compute days_since_last_donation.
    """
    stats = history_stats or {}
    blood_group = _get(donor, "blood_group") or "O+"
    last_type = _get(donor, "last_donation_type") or ""

    reference = None
    if sim_time is not None:
        reference = EPOCH + dt.timedelta(minutes=float(sim_time))

    feats = {
        "age": float(_get(donor, "age") or 0.0),
        "sex": 1.0 if (_get(donor, "sex") or "M") == "F" else 0.0,
        "weight_kg": float(_get(donor, "weight_kg") or 0.0),
        "notified_90d": float(_get(donor, "notified_90d") or 0.0),
        "days_since_last_donation": days_since(_get(donor, "last_donation_at"), reference),
        "quiet_window_len": quiet_window_len(
            _get(donor, "quiet_start_hour"), _get(donor, "quiet_end_hour")
        ),
        "hist_notified": float(stats.get("hist_notified", 0.0) or 0.0),
        "hist_responded": float(stats.get("hist_responded", 0.0) or 0.0),
        "hist_accepted": float(stats.get("hist_accepted", 0.0) or 0.0),
        "hist_donated": float(stats.get("hist_donated", 0.0) or 0.0),
        "accept_rate": float(stats.get("accept_rate", 0.0) or 0.0),
        "donate_rate": float(stats.get("donate_rate", 0.0) or 0.0),
        "mean_response_delay_min": float(stats.get("mean_response_delay_min", 0.0) or 0.0),
        "days_since_last_notified": float(stats.get("days_since_last_notified", 0.0) or 0.0),
    }
    for group in BLOOD_GROUPS:
        feats[f"bg_{group}"] = 1.0 if blood_group == group else 0.0
    for dtype in DONATION_TYPES:
        feats[f"dt_{dtype}"] = 1.0 if last_type == dtype else 0.0
    return feats


def ordered_feature_vector(feats, feature_order):
    """Project a feature dict onto the frozen column order (missing -> 0.0)."""
    return [float(feats.get(name, 0.0)) for name in feature_order]
