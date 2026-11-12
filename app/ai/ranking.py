"""AI-driven donor ranking strategy (competition module C1).

Implements the ``DonorRankingStrategy`` protocol defined by DEV-01 in
``app/domain/ranking.py``. The import is lazy so this module stays
importable before the backend protocol lands; if it is missing, minimal
local stand-ins keep the class definition valid (tests and scripts run
independently).

Rules: fully local (scikit-learn artifact committed in ``app/ai/model/``),
input = numeric donor features, output = P(accepted) in [0, 1], no external
services, no exceptions ever escape :meth:`rank` (fallback = travel-time
ranking).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

try:  # protocol defined by DEV-01 (backend core)
    from app.domain.ranking import DonorRankingStrategy, RankedDonor, RankingContext  # noqa: F401
except ImportError:  # backend not merged yet — local stand-ins
    @dataclass
    class RankedDonor:
        donor_id: str
        score: float
        travel_minutes: float = 0.0

    class DonorRankingStrategy:  # pragma: no cover - protocol stand-in
        name = ""

    class RankingContext:  # pragma: no cover - protocol stand-in
        pass

from app.ai.features import build_donor_features, ordered_feature_vector

logger = logging.getLogger(__name__)

FALLBACK_TRAVEL_PENALTY = 1e9


def _get(obj, name, default=None):
    if obj is None:
        return default
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict) and name in obj:
        return obj[name]
    return default


class AIResponseRankingStrategy:
    """Rank donors by P(accepted) from a local logistic-regression model.

    Ties are broken by ascending travel time. When the model artifact is
    missing or fails to load, the strategy degrades gracefully to pure
    travel-time ranking (score = -travel_minutes).
    """

    name = "ai_response"

    def __init__(self, model_path: str):
        self.model_path = str(model_path)
        self.available = False
        self.pipeline = None
        self.feature_order = []
        try:
            import joblib

            model_file = Path(self.model_path)
            self.pipeline = joblib.load(model_file)
            config_file = model_file.parent / "feature_config.json"
            self.feature_order = json.loads(config_file.read_text(encoding="utf-8"))["features"]
            if not self.feature_order:
                raise ValueError("feature_config.json has empty feature list")
            self.available = True
        except Exception as exc:
            logger.warning("AI ranking model unavailable at %s (%s) — travel-time fallback.", self.model_path, exc)
            self.available = False

    def rank(self, donors, context):
        travel = _get(context, "travel_minutes", None) or {}
        history_stats = _get(context, "history_stats", None) or {}
        sim_time = _get(context, "sim_min", None)
        if isinstance(travel, dict):
            travel_get = lambda donor_id: travel.get(donor_id, FALLBACK_TRAVEL_PENALTY)  # noqa: E731
        else:
            travel_get = lambda donor_id: _get(travel, donor_id, FALLBACK_TRAVEL_PENALTY)  # noqa: E731

        ranked = []
        for donor in donors:
            donor_id = _get(donor, "donor_id")
            travel_minutes = float(travel_get(donor_id) or FALLBACK_TRAVEL_PENALTY)
            score = -travel_minutes  # fallback: travel-time ranking
            if self.available:
                try:
                    feats = build_donor_features(donor, history_stats.get(donor_id), sim_time=sim_time)
                    row = [ordered_feature_vector(feats, self.feature_order)]
                    proba = self.pipeline.predict_proba(row)
                    score = float(proba[0][1])
                except Exception as exc:
                    logger.warning("AI scoring failed for donor %s (%s) — travel fallback.", donor_id, exc)
                    score = -travel_minutes
            ranked.append(RankedDonor(donor_id=donor_id, score=score, travel_minutes=travel_minutes))

        ranked.sort(key=lambda item: (-item.score, item.travel_minutes))
        return ranked
